/* -*- Mode: C; tab-width: 8; indent-tabs-mode: t; c-basic-offset: 8 -*-
 *
 * Copyright (C) 2008 Richard Hughes <richard@hughsie.com>
 *
 * Licensed under the GNU General Public License Version 2
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, write to the Free Software
 * Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
 */

/**
 * SECTION:pk-control
 * @short_description: For querying data about PackageKit
 *
 * A GObject to use for accessing PackageKit asynchronously.
 */

#include "config.h"

#include <string.h>
#include <glib-object.h>
#include <dbus/dbus-glib.h>
#include <gio/gio.h>

#include <packagekit-glib2/pk-bitfield.h>
#include <packagekit-glib2/pk-common.h>
#include <packagekit-glib2/pk-control.h>
#include <packagekit-glib2/pk-version.h>

#include "egg-debug.h"

static void     pk_control_finalize	(GObject     *object);

#define PK_CONTROL_GET_PRIVATE(o) (G_TYPE_INSTANCE_GET_PRIVATE ((o), PK_TYPE_CONTROL, PkControlPrivate))

/**
 * PkControlPrivate:
 *
 * Private #PkControl data
 **/
struct _PkControlPrivate
{
	GPtrArray		*calls;
	DBusGProxy		*proxy;
	DBusGProxy		*proxy_props;
	DBusGProxy		*proxy_dbus;
	DBusGConnection		*connection;
	gboolean		 version_major;
	gboolean		 version_minor;
	gboolean		 version_micro;
	gchar			*backend_name;
	gchar			*backend_description;
	gchar			*backend_author;
	PkBitfield		 roles;
	PkBitfield		 groups;
	PkBitfield		 filters;
	gchar			*mime_types;
};

enum {
	SIGNAL_LOCKED,
	SIGNAL_LIST_CHANGED,
	SIGNAL_RESTART_SCHEDULE,
	SIGNAL_UPDATES_CHANGED,
	SIGNAL_REPO_LIST_CHANGED,
	SIGNAL_NETWORK_STATE_CHANGED,
	SIGNAL_CONNECTION_CHANGED,
	SIGNAL_LAST
};

enum {
	PROP_0,
	PROP_VERSION_MAJOR,
	PROP_VERSION_MINOR,
	PROP_VERSION_MICRO,
	PROP_BACKEND_NAME,
	PROP_BACKEND_DESCRIPTION,
	PROP_BACKEND_AUTHOR,
	PROP_ROLES,
	PROP_GROUPS,
	PROP_FILTERS,
	PROP_MIME_TYPES,
	PROP_LAST
};

static guint signals [SIGNAL_LAST] = { 0 };
static gpointer pk_control_object = NULL;

G_DEFINE_TYPE (PkControl, pk_control, G_TYPE_OBJECT)

typedef struct {
	gboolean		 ret;
	gchar			*tid;
	gchar			**transaction_list;
	gchar			*daemon_state;
	guint			 time;
	DBusGProxyCall		*call;
	GCancellable		*cancellable;
	GSimpleAsyncResult	*res;
	PkAuthorizeEnum		 authorize;
	PkControl		*control;
	PkNetworkEnum		 network;
} PkControlState;

/* tiny helper to help us do the async operation */
typedef struct {
	GError		**error;
	GMainLoop	*loop;
	gboolean	 ret;
	guint		 seconds;
} PkControlHelper;

/**
 * pk_control_error_quark:
 *
 * We are a GObject that sets errors
 *
 * Return value: Our personal error quark.
 **/
GQuark
pk_control_error_quark (void)
{
	static GQuark quark = 0;
	if (!quark)
		quark = g_quark_from_static_string ("pk_control_error");
	return quark;
}

/**
 * pk_control_fixup_dbus_error:
 **/
static void
pk_control_fixup_dbus_error (GError *error)
{
	g_return_if_fail (error != NULL);

	/* hardcode domain */
	error->domain = PK_CONTROL_ERROR;

	/* find a better failure code */
	if (error->code == DBUS_GERROR_SPAWN_CHILD_EXITED)
		error->code = PK_CONTROL_ERROR_CANNOT_START_DAEMON;
	else
		error->code = PK_CONTROL_ERROR_FAILED;
}

/***************************************************************************************************/

/**
 * pk_control_get_tid_state_finish:
 **/
static void
pk_control_get_tid_state_finish (PkControlState *state, GError *error)
{
	/* remove weak ref */
	if (state->control != NULL)
		g_object_remove_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* get result */
	if (state->tid != NULL) {
		g_simple_async_result_set_op_res_gpointer (state->res, g_strdup (state->tid), g_free);
	} else {
		g_simple_async_result_set_from_error (state->res, error);
		g_error_free (error);
	}

	/* remove from list */
	g_ptr_array_remove (state->control->priv->calls, state);

	/* complete */
	g_simple_async_result_complete_in_idle (state->res);

	/* deallocate */
	if (state->cancellable != NULL)
		g_object_unref (state->cancellable);
	g_free (state->tid);
	g_object_unref (state->res);
	g_slice_free (PkControlState, state);
}

/**
 * pk_control_get_tid_cb:
 **/
static void
pk_control_get_tid_cb (DBusGProxy *proxy, DBusGProxyCall *call, PkControlState *state)
{
	GError *error = NULL;
	gchar *tid = NULL;
	gboolean ret;

	/* finished this call */
	state->call = NULL;

	/* get the result */
	ret = dbus_g_proxy_end_call (proxy, call, &error,
				     G_TYPE_STRING, &tid,
				     G_TYPE_INVALID);
	if (!ret) {
		/* fix up the D-Bus error */
		pk_control_fixup_dbus_error (error);
		egg_warning ("failed: %s", error->message);
		pk_control_get_tid_state_finish (state, error);
		goto out;
	}

	/* save results */
	state->tid = g_strdup (tid);

	/* we're done */
	pk_control_get_tid_state_finish (state, error);
out:
	g_free (tid);
}

/**
 * pk_control_get_tid_async:
 * @control: a valid #PkControl instance
 * @cancellable: a #GCancellable or %NULL
 * @callback: the function to run on completion
 * @user_data: the data to pass to @callback
 *
 * Gets a transacton ID from the daemon.
 **/
void
pk_control_get_tid_async (PkControl *control, GCancellable *cancellable, GAsyncReadyCallback callback, gpointer user_data)
{
	GSimpleAsyncResult *res;
	PkControlState *state;

	g_return_if_fail (PK_IS_CONTROL (control));
	g_return_if_fail (callback != NULL);

	res = g_simple_async_result_new (G_OBJECT (control), callback, user_data, pk_control_get_tid_async);

	/* save state */
	state = g_slice_new0 (PkControlState);
	state->res = g_object_ref (res);
	if (cancellable != NULL)
		state->cancellable = g_object_ref (cancellable);
	state->control = control;
	g_object_add_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* call D-Bus method async */
	state->call = dbus_g_proxy_begin_call (control->priv->proxy, "GetTid",
					       (DBusGProxyCallNotify) pk_control_get_tid_cb, state,
					       NULL, G_TYPE_INVALID);

	/* track state */
	g_ptr_array_add (control->priv->calls, state);

	g_object_unref (res);
}

/**
 * pk_control_get_tid_finish:
 * @control: a valid #PkControl instance
 * @res: the #GAsyncResult
 * @error: A #GError or %NULL
 *
 * Gets the result from the asynchronous function.
 *
 * Return value: the ID, or %NULL if unset, free with g_free()
 **/
gchar *
pk_control_get_tid_finish (PkControl *control, GAsyncResult *res, GError **error)
{
	GSimpleAsyncResult *simple;
	gpointer source_tag;

	g_return_val_if_fail (PK_IS_CONTROL (control), NULL);
	g_return_val_if_fail (G_IS_SIMPLE_ASYNC_RESULT (res), NULL);
	g_return_val_if_fail (error == NULL || *error == NULL, NULL);

	simple = G_SIMPLE_ASYNC_RESULT (res);
	source_tag = g_simple_async_result_get_source_tag (simple);

	g_return_val_if_fail (source_tag == pk_control_get_tid_async, NULL);

	if (g_simple_async_result_propagate_error (simple, error))
		return NULL;

	return g_strdup (g_simple_async_result_get_op_res_gpointer (simple));
}

/***************************************************************************************************/

/**
 * pk_control_get_daemon_state_state_finish:
 **/
static void
pk_control_get_daemon_state_state_finish (PkControlState *state, GError *error)
{
	/* remove weak ref */
	if (state->control != NULL)
		g_object_remove_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* get result */
	if (state->daemon_state != NULL) {
		g_simple_async_result_set_op_res_gpointer (state->res, g_strdup (state->daemon_state), g_free);
	} else {
		g_simple_async_result_set_from_error (state->res, error);
		g_error_free (error);
	}

	/* remove from list */
	g_ptr_array_remove (state->control->priv->calls, state);

	/* complete */
	g_simple_async_result_complete_in_idle (state->res);

	/* deallocate */
	if (state->cancellable != NULL)
		g_object_unref (state->cancellable);
	g_free (state->daemon_state);
	g_object_unref (state->res);
	g_slice_free (PkControlState, state);
}

/**
 * pk_control_get_daemon_state_cb:
 **/
static void
pk_control_get_daemon_state_cb (DBusGProxy *proxy, DBusGProxyCall *call, PkControlState *state)
{
	GError *error = NULL;
	gchar *daemon_state = NULL;
	gboolean ret;

	/* finished this call */
	state->call = NULL;

	/* get the result */
	ret = dbus_g_proxy_end_call (proxy, call, &error,
				     G_TYPE_STRING, &daemon_state,
				     G_TYPE_INVALID);
	if (!ret) {
		/* fix up the D-Bus error */
		pk_control_fixup_dbus_error (error);
		egg_warning ("failed: %s", error->message);
		pk_control_get_daemon_state_state_finish (state, error);
		goto out;
	}

	/* save results */
	state->daemon_state = g_strdup (daemon_state);

	/* we're done */
	pk_control_get_daemon_state_state_finish (state, error);
out:
	g_free (daemon_state);
}

/**
 * pk_control_get_daemon_state_async:
 * @control: a valid #PkControl instance
 * @cancellable: a #GCancellable or %NULL
 * @callback: the function to run on completion
 * @user_data: the data to pass to @callback
 *
 * Gets the debugging state from the daemon.
 **/
void
pk_control_get_daemon_state_async (PkControl *control, GCancellable *cancellable, GAsyncReadyCallback callback, gpointer user_data)
{
	GSimpleAsyncResult *res;
	PkControlState *state;

	g_return_if_fail (PK_IS_CONTROL (control));
	g_return_if_fail (callback != NULL);

	res = g_simple_async_result_new (G_OBJECT (control), callback, user_data, pk_control_get_daemon_state_async);

	/* save state */
	state = g_slice_new0 (PkControlState);
	state->res = g_object_ref (res);
	if (cancellable != NULL)
		state->cancellable = g_object_ref (cancellable);
	state->control = control;
	g_object_add_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* call D-Bus method async */
	state->call = dbus_g_proxy_begin_call (control->priv->proxy, "GetDaemonState",
					       (DBusGProxyCallNotify) pk_control_get_daemon_state_cb, state,
					       NULL, G_TYPE_INVALID);

	/* track state */
	g_ptr_array_add (control->priv->calls, state);

	g_object_unref (res);
}

/**
 * pk_control_get_daemon_state_finish:
 * @control: a valid #PkControl instance
 * @res: the #GAsyncResult
 * @error: A #GError or %NULL
 *
 * Gets the result from the asynchronous function.
 *
 * Return value: the ID, or %NULL if unset, free with g_free()
 **/
gchar *
pk_control_get_daemon_state_finish (PkControl *control, GAsyncResult *res, GError **error)
{
	GSimpleAsyncResult *simple;
	gpointer source_tag;

	g_return_val_if_fail (PK_IS_CONTROL (control), NULL);
	g_return_val_if_fail (G_IS_SIMPLE_ASYNC_RESULT (res), NULL);
	g_return_val_if_fail (error == NULL || *error == NULL, NULL);

	simple = G_SIMPLE_ASYNC_RESULT (res);
	source_tag = g_simple_async_result_get_source_tag (simple);

	g_return_val_if_fail (source_tag == pk_control_get_daemon_state_async, NULL);

	if (g_simple_async_result_propagate_error (simple, error))
		return NULL;

	return g_strdup (g_simple_async_result_get_op_res_gpointer (simple));
}

/***************************************************************************************************/

/**
 * pk_control_set_proxy_state_finish:
 **/
static void
pk_control_set_proxy_state_finish (PkControlState *state, GError *error)
{
	/* remove weak ref */
	if (state->control != NULL)
		g_object_remove_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* get result */
	if (state->ret) {
		g_simple_async_result_set_op_res_gboolean (state->res, state->ret);
	} else {
		g_simple_async_result_set_from_error (state->res, error);
		g_error_free (error);
	}

	/* remove from list */
	g_ptr_array_remove (state->control->priv->calls, state);

	/* complete */
	g_simple_async_result_complete_in_idle (state->res);

	/* deallocate */
	if (state->cancellable != NULL)
		g_object_unref (state->cancellable);
	g_object_unref (state->res);
	g_slice_free (PkControlState, state);
}

/**
 * pk_control_set_proxy_cb:
 **/
static void
pk_control_set_proxy_cb (DBusGProxy *proxy, DBusGProxyCall *call, PkControlState *state)
{
	GError *error = NULL;
	gchar *tid = NULL;
	gboolean ret;

	/* finished this call */
	state->call = NULL;

	/* get the result */
	ret = dbus_g_proxy_end_call (proxy, call, &error,
				     G_TYPE_INVALID);
	if (!ret) {
		egg_warning ("failed to set proxy: %s", error->message);
		pk_control_set_proxy_state_finish (state, error);
		goto out;
	}

	/* save data */
	state->ret = TRUE;

	/* we're done */
	pk_control_set_proxy_state_finish (state, error);
out:
	g_free (tid);
}

/**
 * pk_control_set_proxy_async:
 * @control: a valid #PkControl instance
 * @proxy_http: a HTTP proxy string such as "username:password@server.lan:8080"
 * @proxy_ftp: a FTP proxy string such as "server.lan:8080"
 * @cancellable: a #GCancellable or %NULL
 * @callback: the function to run on completion
 * @user_data: the data to pass to @callback
 *
 * Set a proxy on the PK daemon
 **/
void
pk_control_set_proxy_async (PkControl *control, const gchar *proxy_http, const gchar *proxy_ftp, GCancellable *cancellable,
			    GAsyncReadyCallback callback, gpointer user_data)
{
	GSimpleAsyncResult *res;
	PkControlState *state;

	g_return_if_fail (PK_IS_CONTROL (control));
	g_return_if_fail (callback != NULL);

	res = g_simple_async_result_new (G_OBJECT (control), callback, user_data, pk_control_set_proxy_async);

	/* save state */
	state = g_slice_new0 (PkControlState);
	state->res = g_object_ref (res);
	if (cancellable != NULL)
		state->cancellable = g_object_ref (cancellable);
	state->control = control;
	g_object_add_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* call D-Bus set_proxy async */
	state->call = dbus_g_proxy_begin_call (control->priv->proxy, "SetProxy",
					       (DBusGProxyCallNotify) pk_control_set_proxy_cb, state, NULL,
					       G_TYPE_STRING, proxy_http,
					       G_TYPE_STRING, proxy_ftp,
					       G_TYPE_INVALID);

	/* track state */
	g_ptr_array_add (control->priv->calls, state);

	g_object_unref (res);
}

/**
 * pk_control_set_proxy_finish:
 * @control: a valid #PkControl instance
 * @res: the #GAsyncResult
 * @error: A #GError or %NULL
 *
 * Gets the result from the asynchronous function.
 *
 * Return value: %TRUE if we set the proxy successfully
 **/
gboolean
pk_control_set_proxy_finish (PkControl *control, GAsyncResult *res, GError **error)
{
	GSimpleAsyncResult *simple;
	gpointer source_tag;

	g_return_val_if_fail (PK_IS_CONTROL (control), FALSE);
	g_return_val_if_fail (G_IS_SIMPLE_ASYNC_RESULT (res), FALSE);
	g_return_val_if_fail (error == NULL || *error == NULL, FALSE);

	simple = G_SIMPLE_ASYNC_RESULT (res);
	source_tag = g_simple_async_result_get_source_tag (simple);

	g_return_val_if_fail (source_tag == pk_control_set_proxy_async, FALSE);

	if (g_simple_async_result_propagate_error (simple, error))
		return FALSE;

	return g_simple_async_result_get_op_res_gboolean (simple);
}

/***************************************************************************************************/

/**
 * pk_control_get_transaction_list_state_finish:
 **/
static void
pk_control_get_transaction_list_state_finish (PkControlState *state, GError *error)
{
	/* remove weak ref */
	if (state->control != NULL)
		g_object_remove_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* get result */
	if (state->transaction_list != NULL) {
		g_simple_async_result_set_op_res_gpointer (state->res, g_strdupv (state->transaction_list), (GDestroyNotify) g_strfreev);
	} else {
		g_simple_async_result_set_from_error (state->res, error);
		g_error_free (error);
	}

	/* remove from list */
	g_ptr_array_remove (state->control->priv->calls, state);

	/* complete */
	g_simple_async_result_complete_in_idle (state->res);

	/* deallocate */
	if (state->cancellable != NULL)
		g_object_unref (state->cancellable);
	g_strfreev (state->transaction_list);
	g_object_unref (state->res);
	g_slice_free (PkControlState, state);
}

/**
 * pk_control_get_transaction_list_cb:
 **/
static void
pk_control_get_transaction_list_cb (DBusGProxy *proxy, DBusGProxyCall *call, PkControlState *state)
{
	GError *error = NULL;
	gchar **temp = NULL;
	gboolean ret;

	/* finished this call */
	state->call = NULL;

	/* get the result */
	ret = dbus_g_proxy_end_call (proxy, call, &error,
				     G_TYPE_STRV, &temp,
				     G_TYPE_INVALID);
	if (!ret) {
		/* fix up the D-Bus error */
		pk_control_fixup_dbus_error (error);
		egg_warning ("failed: %s", error->message);
		pk_control_get_transaction_list_state_finish (state, error);
		goto out;
	}

	/* save data */
	state->transaction_list = g_strdupv (temp);

	/* we're done */
	pk_control_get_transaction_list_state_finish (state, error);
out:
	g_strfreev (temp);
}

/**
 * pk_control_get_transaction_list_async:
 * @control: a valid #PkControl instance
 * @cancellable: a #GCancellable or %NULL
 * @callback: the function to run on completion
 * @user_data: the data to pass to @callback
 *
 * Gets the transactions currently running in the daemon.
 **/
void
pk_control_get_transaction_list_async (PkControl *control, GCancellable *cancellable, GAsyncReadyCallback callback, gpointer user_data)
{
	GSimpleAsyncResult *res;
	PkControlState *state;

	g_return_if_fail (PK_IS_CONTROL (control));
	g_return_if_fail (callback != NULL);

	res = g_simple_async_result_new (G_OBJECT (control), callback, user_data, pk_control_get_transaction_list_async);

	/* save state */
	state = g_slice_new0 (PkControlState);
	state->res = g_object_ref (res);
	if (cancellable != NULL)
		state->cancellable = g_object_ref (cancellable);
	state->control = control;
	g_object_add_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* call D-Bus get_transaction_list async */
	state->call = dbus_g_proxy_begin_call (control->priv->proxy, "GetTransactionList",
					       (DBusGProxyCallNotify) pk_control_get_transaction_list_cb, state,
					       NULL, G_TYPE_INVALID);

	/* track state */
	g_ptr_array_add (control->priv->calls, state);

	g_object_unref (res);
}

/**
 * pk_control_get_transaction_list_finish:
 * @control: a valid #PkControl instance
 * @res: the #GAsyncResult
 * @error: A #GError or %NULL
 *
 * Gets the result from the asynchronous function.
 *
 * Return value: A GStrv list of transaction ID's, free with g_strfreev()
 **/
gchar **
pk_control_get_transaction_list_finish (PkControl *control, GAsyncResult *res, GError **error)
{
	GSimpleAsyncResult *simple;
	gpointer source_tag;

	g_return_val_if_fail (PK_IS_CONTROL (control), NULL);
	g_return_val_if_fail (G_IS_SIMPLE_ASYNC_RESULT (res), NULL);
	g_return_val_if_fail (error == NULL || *error == NULL, NULL);

	simple = G_SIMPLE_ASYNC_RESULT (res);
	source_tag = g_simple_async_result_get_source_tag (simple);

	g_return_val_if_fail (source_tag == pk_control_get_transaction_list_async, NULL);

	if (g_simple_async_result_propagate_error (simple, error))
		return NULL;

	return g_strdupv (g_simple_async_result_get_op_res_gpointer (simple));
}

/***************************************************************************************************/

/**
 * pk_control_get_time_since_action_state_finish:
 **/
static void
pk_control_get_time_since_action_state_finish (PkControlState *state, GError *error)
{
	/* remove weak ref */
	if (state->control != NULL)
		g_object_remove_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* get result */
	if (state->time != 0) {
		g_simple_async_result_set_op_res_gssize (state->res, state->time);
	} else {
		g_simple_async_result_set_from_error (state->res, error);
		g_error_free (error);
	}

	/* remove from list */
	g_ptr_array_remove (state->control->priv->calls, state);

	/* complete */
	g_simple_async_result_complete_in_idle (state->res);

	/* deallocate */
	if (state->cancellable != NULL)
		g_object_unref (state->cancellable);
	g_object_unref (state->res);
	g_slice_free (PkControlState, state);
}

/**
 * pk_control_get_time_since_action_cb:
 **/
static void
pk_control_get_time_since_action_cb (DBusGProxy *proxy, DBusGProxyCall *call, PkControlState *state)
{
	GError *error = NULL;
	gboolean ret;
	guint seconds;

	/* finished this call */
	state->call = NULL;

	/* get the result */
	ret = dbus_g_proxy_end_call (proxy, call, &error,
				     G_TYPE_UINT, &seconds,
				     G_TYPE_INVALID);
	if (!ret) {
		/* fix up the D-Bus error */
		pk_control_fixup_dbus_error (error);
		egg_warning ("failed: %s", error->message);
		pk_control_get_time_since_action_state_finish (state, error);
		goto out;
	}

	/* save data */
	state->time = seconds;
	if (state->time == 0) {
		error = g_error_new (PK_CONTROL_ERROR, PK_CONTROL_ERROR_FAILED, "could not get time");
		pk_control_get_time_since_action_state_finish (state, error);
		goto out;
	}

	/* we're done */
	pk_control_get_time_since_action_state_finish (state, error);
out:
	return;
}

/**
 * pk_control_get_time_since_action_async:
 * @control: a valid #PkControl instance
 * @role: the role enum, e.g. %PK_ROLE_ENUM_GET_UPDATES
 * @cancellable: a #GCancellable or %NULL
 * @callback: the function to run on completion
 * @user_data: the data to pass to @callback
 *
 * We may want to know how long it has been since we refreshed the cache or
 * retrieved the update list.
 **/
void
pk_control_get_time_since_action_async (PkControl *control, PkRoleEnum role, GCancellable *cancellable, GAsyncReadyCallback callback, gpointer user_data)
{
	GSimpleAsyncResult *res;
	PkControlState *state;
	const gchar *role_text;

	g_return_if_fail (PK_IS_CONTROL (control));
	g_return_if_fail (callback != NULL);

	res = g_simple_async_result_new (G_OBJECT (control), callback, user_data, pk_control_get_time_since_action_async);

	/* save state */
	state = g_slice_new0 (PkControlState);
	state->res = g_object_ref (res);
	if (cancellable != NULL)
		state->cancellable = g_object_ref (cancellable);
	state->control = control;
	g_object_add_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* call D-Bus get_time_since_action async */
	role_text = pk_role_enum_to_text (role);
	state->call = dbus_g_proxy_begin_call (control->priv->proxy, "GetTimeSinceAction",
					       (DBusGProxyCallNotify) pk_control_get_time_since_action_cb, state, NULL,
					       G_TYPE_STRING, role_text,
					       G_TYPE_INVALID);

	/* track state */
	g_ptr_array_add (control->priv->calls, state);

	g_object_unref (res);
}

/**
 * pk_control_get_time_since_action_finish:
 * @control: a valid #PkControl instance
 * @res: the #GAsyncResult
 * @error: A #GError or %NULL
 *
 * Gets the result from the asynchronous function.
 *
 * Return value: %TRUE if the daemon serviced the request
 **/
guint
pk_control_get_time_since_action_finish (PkControl *control, GAsyncResult *res, GError **error)
{
	GSimpleAsyncResult *simple;
	gpointer source_tag;

	g_return_val_if_fail (PK_IS_CONTROL (control), 0);
	g_return_val_if_fail (G_IS_SIMPLE_ASYNC_RESULT (res), 0);
	g_return_val_if_fail (error == NULL || *error == NULL, 0);

	simple = G_SIMPLE_ASYNC_RESULT (res);
	source_tag = g_simple_async_result_get_source_tag (simple);

	g_return_val_if_fail (source_tag == pk_control_get_time_since_action_async, 0);

	if (g_simple_async_result_propagate_error (simple, error))
		return 0;

	return (guint) g_simple_async_result_get_op_res_gssize (simple);
}

/***************************************************************************************************/

/**
 * pk_control_get_network_state_state_finish:
 **/
static void
pk_control_get_network_state_state_finish (PkControlState *state, GError *error)
{
	/* remove weak ref */
	if (state->control != NULL)
		g_object_remove_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* get result */
	if (state->network != PK_NETWORK_ENUM_UNKNOWN) {
		g_simple_async_result_set_op_res_gssize (state->res, state->network);
	} else {
		g_simple_async_result_set_from_error (state->res, error);
		g_error_free (error);
	}

	/* remove from list */
	g_ptr_array_remove (state->control->priv->calls, state);

	/* complete */
	g_simple_async_result_complete_in_idle (state->res);

	/* deallocate */
	if (state->cancellable != NULL)
		g_object_unref (state->cancellable);
	g_object_unref (state->res);
	g_slice_free (PkControlState, state);
}

/**
 * pk_control_get_network_state_cb:
 **/
static void
pk_control_get_network_state_cb (DBusGProxy *proxy, DBusGProxyCall *call, PkControlState *state)
{
	GError *error = NULL;
	gboolean ret;
	gchar *network_state = NULL;

	/* finished this call */
	state->call = NULL;

	/* get the result */
	ret = dbus_g_proxy_end_call (proxy, call, &error,
				     G_TYPE_STRING, &network_state,
				     G_TYPE_INVALID);
	if (!ret) {
		/* fix up the D-Bus error */
		pk_control_fixup_dbus_error (error);
		egg_warning ("failed: %s", error->message);
		pk_control_get_network_state_state_finish (state, error);
		goto out;
	}

	/* save data */
	state->network = pk_network_enum_from_text (network_state);
	if (state->network == PK_NETWORK_ENUM_UNKNOWN) {
		error = g_error_new (PK_CONTROL_ERROR, PK_CONTROL_ERROR_FAILED, "could not get state");
		pk_control_get_network_state_state_finish (state, error);
		goto out;
	}

	/* we're done */
	pk_control_get_network_state_state_finish (state, error);
out:
	g_free (network_state);
	return;
}

/**
 * pk_control_get_network_state_async:
 * @control: a valid #PkControl instance
 * @cancellable: a #GCancellable or %NULL
 * @callback: the function to run on completion
 * @user_data: the data to pass to @callback
 *
 * Gets the network state.
 **/
void
pk_control_get_network_state_async (PkControl *control, GCancellable *cancellable, GAsyncReadyCallback callback, gpointer user_data)
{
	GSimpleAsyncResult *res;
	PkControlState *state;

	g_return_if_fail (PK_IS_CONTROL (control));
	g_return_if_fail (callback != NULL);

	res = g_simple_async_result_new (G_OBJECT (control), callback, user_data, pk_control_get_network_state_async);

	/* save state */
	state = g_slice_new0 (PkControlState);
	state->res = g_object_ref (res);
	state->network = PK_NETWORK_ENUM_UNKNOWN;
	if (cancellable != NULL)
		state->cancellable = g_object_ref (cancellable);
	state->control = control;
	g_object_add_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* call D-Bus async */
	state->call = dbus_g_proxy_begin_call (control->priv->proxy, "GetNetworkState",
					       (DBusGProxyCallNotify) pk_control_get_network_state_cb, state, NULL,
					       G_TYPE_INVALID);

	/* track state */
	g_ptr_array_add (control->priv->calls, state);

	g_object_unref (res);
}

/**
 * pk_control_get_network_state_finish:
 * @control: a valid #PkControl instance
 * @res: the #GAsyncResult
 * @error: A #GError or %NULL
 *
 * Gets the result from the asynchronous function.
 *
 * Return value: an enumerated network state
 **/
PkNetworkEnum
pk_control_get_network_state_finish (PkControl *control, GAsyncResult *res, GError **error)
{
	GSimpleAsyncResult *simple;
	gpointer source_tag;

	g_return_val_if_fail (PK_IS_CONTROL (control), PK_NETWORK_ENUM_UNKNOWN);
	g_return_val_if_fail (G_IS_SIMPLE_ASYNC_RESULT (res), PK_NETWORK_ENUM_UNKNOWN);

	simple = G_SIMPLE_ASYNC_RESULT (res);
	source_tag = g_simple_async_result_get_source_tag (simple);

	g_return_val_if_fail (source_tag == pk_control_get_network_state_async, PK_NETWORK_ENUM_UNKNOWN);

	if (g_simple_async_result_propagate_error (simple, error))
		return PK_NETWORK_ENUM_UNKNOWN;

	return (PkNetworkEnum) g_simple_async_result_get_op_res_gssize (simple);
}

/***************************************************************************************************/

/**
 * pk_control_can_authorize_state_finish:
 **/
static void
pk_control_can_authorize_state_finish (PkControlState *state, GError *error)
{
	/* remove weak ref */
	if (state->control != NULL)
		g_object_remove_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* get result */
	if (state->authorize != PK_AUTHORIZE_ENUM_UNKNOWN) {
		g_simple_async_result_set_op_res_gssize (state->res, state->authorize);
	} else {
		g_simple_async_result_set_from_error (state->res, error);
		g_error_free (error);
	}

	/* remove from list */
	g_ptr_array_remove (state->control->priv->calls, state);

	/* complete */
	g_simple_async_result_complete_in_idle (state->res);

	/* deallocate */
	if (state->cancellable != NULL)
		g_object_unref (state->cancellable);
	g_object_unref (state->res);
	g_slice_free (PkControlState, state);
}

/**
 * pk_control_can_authorize_cb:
 **/
static void
pk_control_can_authorize_cb (DBusGProxy *proxy, DBusGProxyCall *call, PkControlState *state)
{
	GError *error = NULL;
	gboolean ret;
	gchar *authorize_state = NULL;

	/* finished this call */
	state->call = NULL;

	/* get the result */
	ret = dbus_g_proxy_end_call (proxy, call, &error,
				     G_TYPE_STRING, &authorize_state,
				     G_TYPE_INVALID);
	if (!ret) {
		/* fix up the D-Bus error */
		pk_control_fixup_dbus_error (error);
		egg_warning ("failed: %s", error->message);
		pk_control_can_authorize_state_finish (state, error);
		goto out;
	}

	/* save data */
	state->authorize = pk_authorize_type_enum_from_text (authorize_state);
	if (state->authorize == PK_AUTHORIZE_ENUM_UNKNOWN) {
		error = g_error_new (PK_CONTROL_ERROR, PK_CONTROL_ERROR_FAILED, "could not get state");
		pk_control_can_authorize_state_finish (state, error);
		goto out;
	}

	/* we're done */
	pk_control_can_authorize_state_finish (state, error);
out:
	g_free (authorize_state);
	return;
}

/**
 * pk_control_can_authorize_async:
 * @control: a valid #PkControl instance
 * @action_id: The action ID, for instance "org.freedesktop.PackageKit.install-untrusted"
 * @cancellable: a #GCancellable or %NULL
 * @callback: the function to run on completion
 * @user_data: the data to pass to @callback
 *
 * We may want to know before we run a method if we are going to be denied,
 * accepted or challenged for authentication.
 **/
void
pk_control_can_authorize_async (PkControl *control, const gchar *action_id, GCancellable *cancellable, GAsyncReadyCallback callback, gpointer user_data)
{
	GSimpleAsyncResult *res;
	PkControlState *state;

	g_return_if_fail (PK_IS_CONTROL (control));
	g_return_if_fail (callback != NULL);

	res = g_simple_async_result_new (G_OBJECT (control), callback, user_data, pk_control_can_authorize_async);

	/* save state */
	state = g_slice_new0 (PkControlState);
	state->res = g_object_ref (res);
	if (cancellable != NULL)
		state->cancellable = g_object_ref (cancellable);
	state->control = control;
	state->authorize = PK_AUTHORIZE_ENUM_UNKNOWN;
	g_object_add_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* call D-Bus async */
	state->call = dbus_g_proxy_begin_call (control->priv->proxy, "CanAuthorize",
					       (DBusGProxyCallNotify) pk_control_can_authorize_cb, state, NULL,
					       G_TYPE_STRING, action_id,
					       G_TYPE_INVALID);

	/* track state */
	g_ptr_array_add (control->priv->calls, state);

	g_object_unref (res);
}

/**
 * pk_control_can_authorize_finish:
 * @control: a valid #PkControl instance
 * @res: the #GAsyncResult
 * @error: A #GError or %NULL
 *
 * Gets the result from the asynchronous function.
 *
 * Return value: the %PkAuthorizeEnum or %PK_AUTHORIZE_ENUM_UNKNOWN if the method failed
 **/
PkAuthorizeEnum
pk_control_can_authorize_finish (PkControl *control, GAsyncResult *res, GError **error)
{
	GSimpleAsyncResult *simple;
	gpointer source_tag;

	g_return_val_if_fail (PK_IS_CONTROL (control), PK_AUTHORIZE_ENUM_UNKNOWN);
	g_return_val_if_fail (G_IS_SIMPLE_ASYNC_RESULT (res), PK_AUTHORIZE_ENUM_UNKNOWN);

	simple = G_SIMPLE_ASYNC_RESULT (res);
	source_tag = g_simple_async_result_get_source_tag (simple);

	g_return_val_if_fail (source_tag == pk_control_can_authorize_async, PK_AUTHORIZE_ENUM_UNKNOWN);

	if (g_simple_async_result_propagate_error (simple, error))
		return PK_AUTHORIZE_ENUM_UNKNOWN;

	return (PkAuthorizeEnum) g_simple_async_result_get_op_res_gssize (simple);
}

/***************************************************************************************************/

/**
 * pk_control_get_properties_state_finish:
 **/
static void
pk_control_get_properties_state_finish (PkControlState *state, GError *error)
{
	/* remove weak ref */
	if (state->control != NULL)
		g_object_remove_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* get result */
	if (state->ret) {
		g_simple_async_result_set_op_res_gboolean (state->res, state->ret);
	} else {
		g_simple_async_result_set_from_error (state->res, error);
		g_error_free (error);
	}

	/* remove from list */
	g_ptr_array_remove (state->control->priv->calls, state);

	/* complete */
	g_simple_async_result_complete_in_idle (state->res);

	/* deallocate */
	if (state->cancellable != NULL)
		g_object_unref (state->cancellable);
	g_object_unref (state->res);
	g_slice_free (PkControlState, state);
}

/**
 * pk_control_get_properties_collect_cb:
 **/
static void
pk_control_get_properties_collect_cb (const char *key, const GValue *value, PkControl *control)
{
	const gchar *tmp;

	if (g_strcmp0 (key, "version-major") == 0 || g_strcmp0 (key, "VersionMajor") == 0) {
		control->priv->version_major = g_value_get_uint (value);
	} else if (g_strcmp0 (key, "version-minor") == 0 || g_strcmp0 (key, "VersionMinor") == 0) {
		control->priv->version_minor = g_value_get_uint (value);
	} else if (g_strcmp0 (key, "version-micro") == 0 || g_strcmp0 (key, "VersionMicro") == 0) {
		control->priv->version_micro = g_value_get_uint (value);
	} else if (g_strcmp0 (key, "BackendName") == 0) {
		g_free (control->priv->backend_name);
		control->priv->backend_name = g_strdup (g_value_get_string (value));
	} else if (g_strcmp0 (key, "BackendDescription") == 0) {
		g_free (control->priv->backend_description);
		control->priv->backend_description = g_strdup (g_value_get_string (value));
	} else if (g_strcmp0 (key, "BackendAuthor") == 0) {
		g_free (control->priv->backend_author);
		control->priv->backend_author = g_strdup (g_value_get_string (value));
	} else if (g_strcmp0 (key, "MimeTypes") == 0) {
		g_free (control->priv->mime_types);
		control->priv->mime_types = g_strdup (g_value_get_string (value));
	} else if (g_strcmp0 (key, "Roles") == 0) {
		tmp = g_value_get_string (value);
		control->priv->roles = pk_role_bitfield_from_text (tmp);
	} else if (g_strcmp0 (key, "Groups") == 0) {
		tmp = g_value_get_string (value);
		control->priv->groups = pk_group_bitfield_from_text (tmp);
	} else if (g_strcmp0 (key, "Filters") == 0) {
		tmp = g_value_get_string (value);
		control->priv->filters = pk_filter_bitfield_from_text (tmp);
	} else {
		egg_warning ("unhandled property '%s'", key);
	}
}

/**
 * pk_control_get_properties_cb:
 **/
static void
pk_control_get_properties_cb (DBusGProxy *proxy, DBusGProxyCall *call, PkControlState *state)
{
	GError *error = NULL;
	gchar *tid = NULL;
	gboolean ret;
	GHashTable *hash;

	/* finished this call */
	state->call = NULL;

	/* get the result */
	ret = dbus_g_proxy_end_call (proxy, call, &error,
				     dbus_g_type_get_map ("GHashTable", G_TYPE_STRING, G_TYPE_VALUE), &hash,
				     G_TYPE_INVALID);
	if (!ret) {
		egg_warning ("failed to set proxy: %s", error->message);
		pk_control_get_properties_state_finish (state, error);
		goto out;
	}

	/* save data */
	state->ret = TRUE;

	/* process results */
	if (hash != NULL) {
		g_hash_table_foreach (hash, (GHFunc) pk_control_get_properties_collect_cb, state->control);
		g_hash_table_unref (hash);
	}

	/* we're done */
	pk_control_get_properties_state_finish (state, error);
out:
	g_free (tid);
}

/**
 * pk_control_get_properties_async:
 * @control: a valid #PkControl instance
 * @cancellable: a #GCancellable or %NULL
 * @callback: the function to run on completion
 * @user_data: the data to pass to @callback
 *
 * Gets global properties from the daemon.
 **/
void
pk_control_get_properties_async (PkControl *control, GCancellable *cancellable,
				 GAsyncReadyCallback callback, gpointer user_data)
{
	GSimpleAsyncResult *res;
	PkControlState *state;

	g_return_if_fail (PK_IS_CONTROL (control));
	g_return_if_fail (callback != NULL);

	res = g_simple_async_result_new (G_OBJECT (control), callback, user_data, pk_control_get_properties_async);

	/* save state */
	state = g_slice_new0 (PkControlState);
	state->res = g_object_ref (res);
	if (cancellable != NULL)
		state->cancellable = g_object_ref (cancellable);
	state->control = control;
	g_object_add_weak_pointer (G_OBJECT (state->control), (gpointer) &state->control);

	/* call D-Bus get_properties async */
	state->call = dbus_g_proxy_begin_call (control->priv->proxy_props, "GetAll",
					       (DBusGProxyCallNotify) pk_control_get_properties_cb, state, NULL,
					       G_TYPE_STRING, "org.freedesktop.PackageKit",
					       G_TYPE_INVALID);

	/* track state */
	g_ptr_array_add (control->priv->calls, state);

	g_object_unref (res);
}

/**
 * pk_control_get_properties_finish:
 * @control: a valid #PkControl instance
 * @res: the #GAsyncResult
 * @error: A #GError or %NULL
 *
 * Gets the result from the asynchronous function.
 *
 * Return value: %TRUE if we set the proxy successfully
 **/
gboolean
pk_control_get_properties_finish (PkControl *control, GAsyncResult *res, GError **error)
{
	GSimpleAsyncResult *simple;
	gpointer source_tag;

	g_return_val_if_fail (PK_IS_CONTROL (control), FALSE);
	g_return_val_if_fail (G_IS_SIMPLE_ASYNC_RESULT (res), FALSE);
	g_return_val_if_fail (error == NULL || *error == NULL, FALSE);

	simple = G_SIMPLE_ASYNC_RESULT (res);
	source_tag = g_simple_async_result_get_source_tag (simple);

	g_return_val_if_fail (source_tag == pk_control_get_properties_async, FALSE);

	if (g_simple_async_result_propagate_error (simple, error))
		return FALSE;

	return g_simple_async_result_get_op_res_gboolean (simple);
}

/**
 * pk_control_get_properties_sync_cb:
 **/
static void
pk_control_get_properties_sync_cb (PkControl *control, GAsyncResult *res, PkControlHelper *helper)
{
	/* get the result */
	helper->ret = pk_control_get_properties_finish (control, res, helper->error);
	g_main_loop_quit (helper->loop);
}

/**
 * pk_control_get_properties_sync:
 * @control: a valid #PkControl instance
 * @error: A #GError or %NULL
 *
 * Gets the properties the daemon supports.
 * Warning: this function is synchronous, and may block. Do not use it in GUI
 * applications.
 *
 * Return value: %TRUE if the properties were set correctly
 **/
gboolean
pk_control_get_properties_sync (PkControl *control, GError **error)
{
	gboolean ret;
	PkControlHelper *helper;

	g_return_val_if_fail (PK_IS_CONTROL (control), FALSE);
	g_return_val_if_fail (error == NULL || *error == NULL, FALSE);

	/* create temp object */
	helper = g_new0 (PkControlHelper, 1);
	helper->loop = g_main_loop_new (NULL, FALSE);
	helper->error = error;

	/* run async method */
	pk_control_get_properties_async (control, NULL, (GAsyncReadyCallback) pk_control_get_properties_sync_cb, helper);
	g_main_loop_run (helper->loop);

	ret = helper->ret;

	/* free temp object */
	g_main_loop_unref (helper->loop);
	g_free (helper);

	return ret;
}

/***************************************************************************************************/

/**
 * pk_control_transaction_list_changed_cb:
 */
static void
pk_control_transaction_list_changed_cb (DBusGProxy *proxy, gchar **array, PkControl *control)
{
	g_return_if_fail (PK_IS_CONTROL (control));

	egg_debug ("emit transaction-list-changed");
	g_signal_emit (control, signals [SIGNAL_LIST_CHANGED], 0);
}

/**
 * pk_control_restart_schedule_cb:
 */
static void
pk_control_restart_schedule_cb (DBusGProxy *proxy, PkControl *control)
{
	g_return_if_fail (PK_IS_CONTROL (control));

	egg_debug ("emitting restart-schedule");
	g_signal_emit (control, signals [SIGNAL_RESTART_SCHEDULE], 0);

}

/**
 * pk_control_updates_changed_cb:
 */
static void
pk_control_updates_changed_cb (DBusGProxy *proxy, PkControl *control)
{
	g_return_if_fail (PK_IS_CONTROL (control));

	egg_debug ("emitting updates-changed");
	g_signal_emit (control, signals [SIGNAL_UPDATES_CHANGED], 0);

}

/**
 * pk_control_repo_list_changed_cb:
 */
static void
pk_control_repo_list_changed_cb (DBusGProxy *proxy, PkControl *control)
{
	g_return_if_fail (PK_IS_CONTROL (control));

	egg_debug ("emitting repo-list-changed");
	g_signal_emit (control, signals [SIGNAL_REPO_LIST_CHANGED], 0);
}

/**
 * pk_control_network_state_changed_cb:
 */
static void
pk_control_network_state_changed_cb (DBusGProxy *proxy, const gchar *network_text, PkControl *control)
{
	PkNetworkEnum network;
	g_return_if_fail (PK_IS_CONTROL (control));

	network = pk_network_enum_from_text (network_text);
	egg_debug ("emitting network-state-changed: %s", network_text);
	g_signal_emit (control, signals [SIGNAL_NETWORK_STATE_CHANGED], 0, network);
}

/**
 * pk_control_locked_cb:
 */
static void
pk_control_locked_cb (DBusGProxy *proxy, gboolean is_locked, PkControl *control)
{
	egg_debug ("emit locked %i", is_locked);
	g_signal_emit (control , signals [SIGNAL_LOCKED], 0, is_locked);
}

/**
 * pk_control_cancel_all_dbus_methods:
 **/
static gboolean
pk_control_cancel_all_dbus_methods (PkControl *control)
{
	const PkControlState *state;
	guint i;
	GPtrArray *array;

	/* just cancel the call */
	array = control->priv->calls;
	for (i=0; i<array->len; i++) {
		state = g_ptr_array_index (array, i);
		if (state->call == NULL)
			continue;
		egg_debug ("cancel in flight call: %p", state->call);
		dbus_g_proxy_cancel_call (control->priv->proxy, state->call);
	}

	return TRUE;
}

/**
 * pk_control_name_owner_changed_cb:
 **/
static void
pk_control_name_owner_changed_cb (DBusGProxy *proxy, const gchar *name, const gchar *prev, const gchar *new, PkControl *control)
{
	guint new_len;
	guint prev_len;

	g_return_if_fail (PK_IS_CONTROL (control));

	if (control->priv->proxy_dbus == NULL)
		return;

	/* not us */
	if (g_strcmp0 (name, PK_DBUS_SERVICE) != 0)
		return;

	/* ITS4: ignore, not used for allocation */
	new_len = strlen (new);
	/* ITS4: ignore, not used for allocation */
	prev_len = strlen (prev);

	/* something --> nothing */
	if (prev_len != 0 && new_len == 0) {
		g_signal_emit (control, signals [SIGNAL_CONNECTION_CHANGED], 0, FALSE);
		return;
	}

	/* nothing --> something */
	if (prev_len == 0 && new_len != 0) {
		g_signal_emit (control, signals [SIGNAL_CONNECTION_CHANGED], 0, TRUE);
		return;
	}
}

/**
 * pk_control_get_property:
 **/
static void
pk_control_get_property (GObject *object, guint prop_id, GValue *value, GParamSpec *pspec)
{
	PkControl *control = PK_CONTROL (object);
	PkControlPrivate *priv = control->priv;

	switch (prop_id) {
	case PROP_VERSION_MAJOR:
		g_value_set_uint (value, priv->version_major);
		break;
	case PROP_VERSION_MINOR:
		g_value_set_uint (value, priv->version_minor);
		break;
	case PROP_VERSION_MICRO:
		g_value_set_uint (value, priv->version_micro);
		break;
	case PROP_BACKEND_NAME:
		g_value_set_string (value, priv->backend_name);
		break;
	case PROP_BACKEND_DESCRIPTION:
		g_value_set_string (value, priv->backend_description);
		break;
	case PROP_BACKEND_AUTHOR:
		g_value_set_string (value, priv->backend_author);
		break;
	case PROP_ROLES:
		g_value_set_uint64 (value, priv->roles);
		break;
	case PROP_GROUPS:
		g_value_set_uint64 (value, priv->groups);
		break;
	case PROP_FILTERS:
		g_value_set_uint64 (value, priv->filters);
		break;
	case PROP_MIME_TYPES:
		g_value_set_string (value, priv->mime_types);
		break;
	default:
		G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
		break;
	}
}

/**
 * pk_control_set_property:
 **/
static void
pk_control_set_property (GObject *object, guint prop_id, const GValue *value, GParamSpec *pspec)
{
	switch (prop_id) {
	default:
		G_OBJECT_WARN_INVALID_PROPERTY_ID (object, prop_id, pspec);
		break;
	}
}

/**
 * pk_control_class_init:
 * @klass: The PkControlClass
 **/
static void
pk_control_class_init (PkControlClass *klass)
{
	GParamSpec *pspec;
	GObjectClass *object_class = G_OBJECT_CLASS (klass);
	object_class->get_property = pk_control_get_property;
	object_class->set_property = pk_control_set_property;
	object_class->finalize = pk_control_finalize;

	/**
	 * PkControl:version-major:
	 */
	pspec = g_param_spec_uint ("version-major", NULL, NULL,
				   0, G_MAXUINT, 0,
				   G_PARAM_READABLE);
	g_object_class_install_property (object_class, PROP_VERSION_MAJOR, pspec);

	/**
	 * PkControl:version-minor:
	 */
	pspec = g_param_spec_uint ("version-minor", NULL, NULL,
				   0, G_MAXUINT, 0,
				   G_PARAM_READABLE);
	g_object_class_install_property (object_class, PROP_VERSION_MINOR, pspec);

	/**
	 * PkControl:version-micro:
	 */
	pspec = g_param_spec_uint ("version-micro", NULL, NULL,
				   0, G_MAXUINT, 0,
				   G_PARAM_READABLE);
	g_object_class_install_property (object_class, PROP_VERSION_MICRO, pspec);

	/**
	 * PkControl:backend-name:
	 */
	pspec = g_param_spec_string ("backend-name", NULL, NULL,
				     NULL,
				     G_PARAM_READWRITE);
	g_object_class_install_property (object_class, PROP_BACKEND_NAME, pspec);

	/**
	 * PkControl:backend-description:
	 */
	pspec = g_param_spec_string ("backend-description", NULL, NULL,
				     NULL,
				     G_PARAM_READWRITE);
	g_object_class_install_property (object_class, PROP_BACKEND_DESCRIPTION, pspec);

	/**
	 * PkControl:backend-author:
	 */
	pspec = g_param_spec_string ("backend-author", NULL, NULL,
				     NULL,
				     G_PARAM_READWRITE);
	g_object_class_install_property (object_class, PROP_BACKEND_AUTHOR, pspec);

	/**
	 * PkControl:roles:
	 */
	pspec = g_param_spec_uint64 ("roles", NULL, NULL,
				     0, G_MAXUINT64, 0,
				     G_PARAM_READWRITE);
	g_object_class_install_property (object_class, PROP_ROLES, pspec);

	/**
	 * PkControl:groups:
	 */
	pspec = g_param_spec_uint64 ("groups", NULL, NULL,
				     0, G_MAXUINT64, 0,
				     G_PARAM_READWRITE);
	g_object_class_install_property (object_class, PROP_GROUPS, pspec);

	/**
	 * PkControl:filters:
	 */
	pspec = g_param_spec_uint64 ("filters", NULL, NULL,
				     0, G_MAXUINT64, 0,
				     G_PARAM_READWRITE);
	g_object_class_install_property (object_class, PROP_FILTERS, pspec);

	/**
	 * PkControl:mime-types:
	 */
	pspec = g_param_spec_string ("mime-types", NULL, NULL,
				     NULL,
				     G_PARAM_READWRITE);
	g_object_class_install_property (object_class, PROP_MIME_TYPES, pspec);

	/**
	 * PkControl::updates-changed:
	 * @control: the #PkControl instance that emitted the signal
	 *
	 * The ::updates-changed signal is emitted when the update list may have
	 * changed and the control program may have to update some UI.
	 **/
	signals [SIGNAL_UPDATES_CHANGED] =
		g_signal_new ("updates-changed",
			      G_TYPE_FROM_CLASS (object_class), G_SIGNAL_RUN_LAST,
			      G_STRUCT_OFFSET (PkControlClass, updates_changed),
			      NULL, NULL, g_cclosure_marshal_VOID__VOID,
			      G_TYPE_NONE, 0);
	/**
	 * PkControl::repo-list-changed:
	 * @control: the #PkControl instance that emitted the signal
	 *
	 * The ::repo-list-changed signal is emitted when the repo list may have
	 * changed and the control program may have to update some UI.
	 **/
	signals [SIGNAL_REPO_LIST_CHANGED] =
		g_signal_new ("repo-list-changed",
			      G_TYPE_FROM_CLASS (object_class), G_SIGNAL_RUN_LAST,
			      G_STRUCT_OFFSET (PkControlClass, repo_list_changed),
			      NULL, NULL, g_cclosure_marshal_VOID__VOID,
			      G_TYPE_NONE, 0);
	/**
	 * PkControl::network-state-changed:
	 * @control: the #PkControl instance that emitted the signal
	 *
	 * The ::network-state-changed signal is emitted when the network has changed speed or
	 * connections state.
	 **/
	signals [SIGNAL_NETWORK_STATE_CHANGED] =
		g_signal_new ("network-state-changed",
			      G_TYPE_FROM_CLASS (object_class), G_SIGNAL_RUN_LAST,
			      G_STRUCT_OFFSET (PkControlClass, network_state_changed),
			      NULL, NULL, g_cclosure_marshal_VOID__UINT,
			      G_TYPE_NONE, 1, G_TYPE_UINT);
	/**
	 * PkControl::restart-schedule:
	 * @control: the #PkControl instance that emitted the signal
	 *
	 * The ::restart_schedule signal is emitted when the packagekitd service
	 * has been restarted because it has been upgraded.
	 * Client programs should reload themselves when it is convenient to
	 * do so, as old client tools may not be compatable with the new daemon.
	 **/
	signals [SIGNAL_RESTART_SCHEDULE] =
		g_signal_new ("restart-schedule",
			      G_TYPE_FROM_CLASS (object_class), G_SIGNAL_RUN_LAST,
			      G_STRUCT_OFFSET (PkControlClass, restart_schedule),
			      NULL, NULL, g_cclosure_marshal_VOID__VOID,
			      G_TYPE_NONE, 0);
	/**
	 * PkControl::transaction-list-changed:
	 * @control: the #PkControl instance that emitted the signal
	 *
	 * The ::transaction-list-changed signal is emitted when the list
	 * of transactions handled by the daemon is changed.
	 **/
	signals [SIGNAL_LIST_CHANGED] =
		g_signal_new ("transaction-list-changed",
			      G_TYPE_FROM_CLASS (object_class), G_SIGNAL_RUN_LAST,
			      G_STRUCT_OFFSET (PkControlClass, transaction_list_changed),
			      NULL, NULL, g_cclosure_marshal_VOID__VOID,
			      G_TYPE_NONE, 0);
	/**
	 * PkControl::locked:
	 * @control: the #PkControl instance that emitted the signal
	 *
	 * The ::locked signal is emitted when the backend instance has been
	 * locked by PackageKit.
	 * This may mean that other native package tools will not work.
	 **/
	signals [SIGNAL_LOCKED] =
		g_signal_new ("locked",
			      G_TYPE_FROM_CLASS (object_class), G_SIGNAL_RUN_LAST,
			      G_STRUCT_OFFSET (PkControlClass, locked),
			      NULL, NULL, g_cclosure_marshal_VOID__BOOLEAN,
			      G_TYPE_NONE, 1, G_TYPE_BOOLEAN);

	/**
	 * PkControl::connection-changed:
	 * @control: the #PkControl instance that emitted the signal
	 *
	 * The ::connection-changed is emitted when packagekitd is added or
	 * removed from the bus. In this way, a client can know if the daemon
	 * is running.
	 **/
	signals [SIGNAL_CONNECTION_CHANGED] =
		g_signal_new ("connection-changed",
			      G_TYPE_FROM_CLASS (object_class),
			      G_SIGNAL_RUN_LAST,
			      G_STRUCT_OFFSET (PkControlClass, connection_changed),
			      NULL, NULL, g_cclosure_marshal_VOID__BOOLEAN,
			      G_TYPE_NONE, 1, G_TYPE_BOOLEAN);

	g_type_class_add_private (klass, sizeof (PkControlPrivate));
}

/**
 * pk_control_init:
 * @control: This class instance
 **/
static void
pk_control_init (PkControl *control)
{
	GError *error = NULL;

	control->priv = PK_CONTROL_GET_PRIVATE (control);
	control->priv->mime_types = NULL;
	control->priv->backend_name = NULL;
	control->priv->backend_description = NULL;
	control->priv->backend_author = NULL;
	control->priv->calls = g_ptr_array_new ();

	/* check dbus connections, exit if not valid */
	control->priv->connection = dbus_g_bus_get (DBUS_BUS_SYSTEM, &error);
	if (error != NULL) {
		egg_warning ("%s", error->message);
		g_error_free (error);
		g_error ("This program cannot start until you start the dbus system service.");
	}

	/* we maintain a local copy */
	control->priv->version_major = 0;
	control->priv->version_minor = 0;
	control->priv->version_micro = 0;

	/* get a connection to the main interface */
	control->priv->proxy = dbus_g_proxy_new_for_name (control->priv->connection,
							  PK_DBUS_SERVICE, PK_DBUS_PATH,
							  PK_DBUS_INTERFACE);
	if (control->priv->proxy == NULL)
		egg_error ("Cannot connect to PackageKit.");

	/* get a connection to collect properties */
	control->priv->proxy_props = dbus_g_proxy_new_for_name (control->priv->connection,
								PK_DBUS_SERVICE, PK_DBUS_PATH,
								"org.freedesktop.DBus.Properties");
	if (control->priv->proxy_props == NULL)
		egg_error ("Cannot connect to PackageKit.");

	/* get a connection to watch NameOwnerChanged */
	control->priv->proxy_dbus = dbus_g_proxy_new_for_name_owner (control->priv->connection,
								     DBUS_SERVICE_DBUS, DBUS_PATH_DBUS,
								     DBUS_INTERFACE_DBUS, &error);
	if (control->priv->proxy_dbus == NULL) {
		egg_error ("Cannot connect to DBUS: %s", error->message);
		g_error_free (error);
	}

	/* connect to NameOwnerChanged */
	dbus_g_proxy_add_signal (control->priv->proxy_dbus, "NameOwnerChanged",
				 G_TYPE_STRING, G_TYPE_STRING, G_TYPE_STRING, G_TYPE_INVALID);
	dbus_g_proxy_connect_signal (control->priv->proxy_dbus, "NameOwnerChanged",
				     G_CALLBACK (pk_control_name_owner_changed_cb),
				     control, NULL);

	/* don't timeout, as dbus-glib sets the timeout ~25 seconds */
	dbus_g_proxy_set_default_timeout (control->priv->proxy, INT_MAX);

	dbus_g_proxy_add_signal (control->priv->proxy, "TransactionListChanged",
				 G_TYPE_STRV, G_TYPE_INVALID);
	dbus_g_proxy_connect_signal (control->priv->proxy, "TransactionListChanged",
				     G_CALLBACK(pk_control_transaction_list_changed_cb), control, NULL);

	dbus_g_proxy_add_signal (control->priv->proxy, "UpdatesChanged", G_TYPE_INVALID);
	dbus_g_proxy_connect_signal (control->priv->proxy, "UpdatesChanged",
				     G_CALLBACK (pk_control_updates_changed_cb), control, NULL);

	dbus_g_proxy_add_signal (control->priv->proxy, "RepoListChanged", G_TYPE_INVALID);
	dbus_g_proxy_connect_signal (control->priv->proxy, "RepoListChanged",
				     G_CALLBACK (pk_control_repo_list_changed_cb), control, NULL);

	dbus_g_proxy_add_signal (control->priv->proxy, "NetworkStateChanged",
				 G_TYPE_STRING, G_TYPE_INVALID);
	dbus_g_proxy_connect_signal (control->priv->proxy, "NetworkStateChanged",
				     G_CALLBACK (pk_control_network_state_changed_cb), control, NULL);

	dbus_g_proxy_add_signal (control->priv->proxy, "RestartSchedule", G_TYPE_INVALID);
	dbus_g_proxy_connect_signal (control->priv->proxy, "RestartSchedule",
				     G_CALLBACK (pk_control_restart_schedule_cb), control, NULL);

	dbus_g_object_register_marshaller (g_cclosure_marshal_VOID__BOOLEAN,
					   G_TYPE_NONE, G_TYPE_BOOLEAN, G_TYPE_INVALID);
	dbus_g_proxy_add_signal (control->priv->proxy, "Locked", G_TYPE_BOOLEAN, G_TYPE_INVALID);
	dbus_g_proxy_connect_signal (control->priv->proxy, "Locked",
				     G_CALLBACK (pk_control_locked_cb), control, NULL);
}

/**
 * pk_control_finalize:
 * @object: The object to finalize
 **/
static void
pk_control_finalize (GObject *object)
{
	PkControl *control = PK_CONTROL (object);
	PkControlPrivate *priv = control->priv;

	/* ensure we cancel any in-flight DBus calls */
	pk_control_cancel_all_dbus_methods (control);

	/* disconnect signal handlers */
	dbus_g_proxy_disconnect_signal (control->priv->proxy, "Locked",
				        G_CALLBACK (pk_control_locked_cb), control);
	dbus_g_proxy_disconnect_signal (control->priv->proxy, "TransactionListChanged",
				        G_CALLBACK (pk_control_transaction_list_changed_cb), control);
	dbus_g_proxy_disconnect_signal (control->priv->proxy, "UpdatesChanged",
				        G_CALLBACK (pk_control_updates_changed_cb), control);
	dbus_g_proxy_disconnect_signal (control->priv->proxy, "RepoListChanged",
				        G_CALLBACK (pk_control_repo_list_changed_cb), control);
	dbus_g_proxy_disconnect_signal (control->priv->proxy, "NetworkStateChanged",
				        G_CALLBACK (pk_control_network_state_changed_cb), control);
	dbus_g_proxy_disconnect_signal (control->priv->proxy, "RestartSchedule",
				        G_CALLBACK (pk_control_restart_schedule_cb), control);
	dbus_g_proxy_disconnect_signal (control->priv->proxy_dbus, "NameOwnerChanged",
				        G_CALLBACK (pk_control_name_owner_changed_cb), control);

	g_free (priv->backend_name);
	g_free (priv->backend_description);
	g_free (priv->backend_author);
	g_free (priv->mime_types);
	g_object_unref (G_OBJECT (priv->proxy));
	g_object_unref (G_OBJECT (priv->proxy_props));
	g_object_unref (G_OBJECT (priv->proxy_dbus));
	g_ptr_array_unref (control->priv->calls);

	G_OBJECT_CLASS (pk_control_parent_class)->finalize (object);
}

/**
 * pk_control_new:
 *
 * Return value: a new PkControl object.
 **/
PkControl *
pk_control_new (void)
{
	if (pk_control_object != NULL) {
		g_object_ref (pk_control_object);
	} else {
		pk_control_object = g_object_new (PK_TYPE_CONTROL, NULL);
		g_object_add_weak_pointer (pk_control_object, &pk_control_object);
	}
	return PK_CONTROL (pk_control_object);
}

/***************************************************************************
 ***                          MAKE CHECK TESTS                           ***
 ***************************************************************************/
#ifdef EGG_TEST
#include "egg-test.h"

static void
pk_control_test_get_tid_cb (GObject *object, GAsyncResult *res, EggTest *test)
{
	PkControl *control = PK_CONTROL (object);
	GError *error = NULL;
	gchar *tid;

	/* get the result */
	tid = pk_control_get_tid_finish (control, res, &error);
	if (tid == NULL) {
		egg_test_failed (test, "failed to get transaction: %s", error->message);
		g_error_free (error);
		return;
	}

	egg_debug ("tid = %s", tid);
	g_free (tid);
	egg_test_loop_quit (test);
}

static void
pk_control_test_get_properties_cb (GObject *object, GAsyncResult *res, EggTest *test)
{
	PkControl *control = PK_CONTROL (object);
	GError *error = NULL;
	gboolean ret;
	PkBitfield roles;
	PkBitfield filters;
	PkBitfield groups;
	gchar *text;

	/* get the result */
	ret = pk_control_get_properties_finish (control, res, &error);
	if (!ret) {
		egg_test_failed (test, "failed to get properties: %s", error->message);
		g_error_free (error);
		return;
	}

	/* get values */
	g_object_get (control,
		      "mime-types", &text,
		      "roles", &roles,
		      "filters", &filters,
		      "groups", &groups,
		      NULL);

	/* check mime_types */
	if (g_strcmp0 (text, "application/x-rpm;application/x-deb") != 0) {
		egg_test_failed (test, "data incorrect: %s", text);
		return;
	}
	g_free (text);

	/* check roles */
	text = pk_role_bitfield_to_text (roles);
	if (g_strcmp0 (text, "cancel;get-depends;get-details;get-files;get-packages;get-repo-list;"
			     "get-requires;get-update-detail;get-updates;install-files;install-packages;"
			     "refresh-cache;remove-packages;repo-enable;repo-set-data;resolve;rollback;"
			     "search-details;search-file;search-group;search-name;update-packages;update-system;"
			     "what-provides;download-packages;get-distro-upgrades;simulate-install-packages;"
			     "simulate-remove-packages;simulate-update-packages") != 0) {
		egg_test_failed (test, "data incorrect: %s", text);
		return;
	}
	g_free (text);

	/* check filters */
	text = pk_filter_bitfield_to_text (filters);
	if (g_strcmp0 (text, "installed;devel;gui") != 0) {
		egg_test_failed (test, "data incorrect: %s", text);
		return;
	}
	g_free (text);

	/* check groups */
	text = pk_group_bitfield_to_text (groups);
	if (g_strcmp0 (text, "accessibility;games;system") != 0) {
		egg_test_failed (test, "data incorrect: %s", text);
		return;
	}
	g_free (text);

	egg_test_loop_quit (test);
}

static void
pk_control_test_get_time_since_action_cb (GObject *object, GAsyncResult *res, EggTest *test)
{
	PkControl *control = PK_CONTROL (object);
	GError *error = NULL;
	guint seconds;

	/* get the result */
	seconds = pk_control_get_time_since_action_finish (control, res, &error);
	if (seconds == 0) {
		egg_test_failed (test, "failed to get time: %s", error->message);
		g_error_free (error);
		return;
	}

	egg_test_loop_quit (test);
}

static void
pk_control_test_get_network_state_cb (GObject *object, GAsyncResult *res, EggTest *test)
{
	PkControl *control = PK_CONTROL (object);
	GError *error = NULL;
	PkNetworkEnum network;

	/* get the result */
	network = pk_control_get_network_state_finish (control, res, &error);
	if (network == PK_NETWORK_ENUM_UNKNOWN) {
		egg_test_failed (test, "failed to get network state: %s", error->message);
		g_error_free (error);
		return;
	}

	egg_test_loop_quit (test);
}

static void
pk_control_test_can_authorize_cb (GObject *object, GAsyncResult *res, EggTest *test)
{
	PkControl *control = PK_CONTROL (object);
	GError *error = NULL;
	PkAuthorizeEnum auth;

	/* get the result */
	auth = pk_control_can_authorize_finish (control, res, &error);
	if (auth == PK_AUTHORIZE_ENUM_UNKNOWN) {
		egg_test_failed (test, "failed to get auth: %s", error->message);
		g_error_free (error);
		return;
	}

	egg_test_loop_quit (test);
}

void
pk_control_test (gpointer user_data)
{
	EggTest *test = (EggTest *) user_data;
	PkControl *control;
	guint version;
	GError *error = NULL;
	gboolean ret;
	gchar *text;
	PkBitfield roles;

	if (!egg_test_start (test, "PkControl"))
		return;

	/************************************************************/
	egg_test_title (test, "get control");
	control = pk_control_new ();
	egg_test_assert (test, control != NULL);

	/************************************************************/
	egg_test_title (test, "get TID async");
	pk_control_get_tid_async (control, NULL, (GAsyncReadyCallback) pk_control_test_get_tid_cb, test);
	egg_test_loop_wait (test, 5000);
	egg_test_success (test, "got tid in %i", egg_test_elapsed (test));

	/************************************************************/
	egg_test_title (test, "get properties async");
	pk_control_get_properties_async (control, NULL, (GAsyncReadyCallback) pk_control_test_get_properties_cb, test);
	egg_test_loop_wait (test, 5000);
	egg_test_success (test, "got properties types in %i", egg_test_elapsed (test));

	/************************************************************/
	egg_test_title (test, "get properties async (again, to test caching)");
	pk_control_get_properties_async (control, NULL, (GAsyncReadyCallback) pk_control_test_get_properties_cb, test);
	egg_test_loop_wait (test, 5000);
	egg_test_success (test, "got properties in %i", egg_test_elapsed (test));

	/************************************************************/
	egg_test_title (test, "get time since async");
	pk_control_get_time_since_action_async (control, PK_ROLE_ENUM_GET_UPDATES, NULL, (GAsyncReadyCallback) pk_control_test_get_time_since_action_cb, test);
	egg_test_loop_wait (test, 5000);
	egg_test_success (test, "got get time since in %i", egg_test_elapsed (test));

	/************************************************************/
	egg_test_title (test, "get network state async");
	pk_control_get_network_state_async (control, NULL, (GAsyncReadyCallback) pk_control_test_get_network_state_cb, test);
	egg_test_loop_wait (test, 5000);
	egg_test_success (test, "get network state in %i", egg_test_elapsed (test));

	/************************************************************/
	egg_test_title (test, "get auth state async");
	pk_control_can_authorize_async (control, "org.freedesktop.packagekit.system-update", NULL,
					(GAsyncReadyCallback) pk_control_test_can_authorize_cb, test);
	egg_test_loop_wait (test, 5000);
	egg_test_success (test, "get auth state in %i", egg_test_elapsed (test));

	/************************************************************/
	egg_test_title (test, "version major");
	g_object_get (control, "version-major", &version, NULL);
	egg_test_assert (test, (version == PK_MAJOR_VERSION));

	/************************************************************/
	egg_test_title (test, "version minor");
	g_object_get (control, "version-minor", &version, NULL);
	egg_test_assert (test, (version == PK_MINOR_VERSION));

	/************************************************************/
	egg_test_title (test, "version micro");
	g_object_get (control, "version-micro", &version, NULL);
	egg_test_assert (test, (version == PK_MICRO_VERSION));

	/************************************************************/
	egg_test_title (test, "get properties sync");
	ret = pk_control_get_properties_sync (control, &error);
	if (!ret)
		egg_test_failed (test, "failed to get properties: %s", error->message);

	/* get data */
	g_object_get (control,
		      "roles", &roles,
		      NULL);

	/* check data */
	text = pk_role_bitfield_to_text (roles);
	if (g_strcmp0 (text, "cancel;get-depends;get-details;get-files;get-packages;get-repo-list;"
			     "get-requires;get-update-detail;get-updates;install-files;install-packages;"
			     "refresh-cache;remove-packages;repo-enable;repo-set-data;resolve;rollback;"
			     "search-details;search-file;search-group;search-name;update-packages;update-system;"
			     "what-provides;download-packages;get-distro-upgrades;simulate-install-packages;"
			     "simulate-remove-packages;simulate-update-packages") != 0) {
		egg_test_failed (test, "data incorrect: %s", text);
	}
	egg_test_success (test, "got correct roles");
	g_free (text);

	g_object_unref (control);
	egg_test_end (test);
}
#endif
