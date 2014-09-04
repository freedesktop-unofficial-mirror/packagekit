/* -*- Mode: C; tab-width: 8; indent-tabs-mode: t; c-basic-offset: 8 -*-
 *
 * Copyright (C) 2007-2014 Richard Hughes <richard@hughsie.com>
 *
 * Licensed under the GNU Lesser General Public License Version 2.1
 *
 * This library is free software; you can redistribute it and/or
 * modify it under the terms of the GNU Lesser General Public
 * License as published by the Free Software Foundation; either
 * version 2.1 of the License, or (at your option) any later version.
 *
 * This library is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public
 * License along with this library; if not, write to the Free Software
 * Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
 */

#include "config.h"

#include <glib-object.h>

#include "src/pk-cleanup.h"

#include "pk-common.h"
#include "pk-debug.h"
#include "pk-enum.h"
#include "pk-package.h"
#include "pk-package-id.h"
#include "pk-package-ids.h"
#include "pk-progress-bar.h"
#include "pk-results.h"

static void
pk_test_bitfield_func (void)
{
	gchar *text;
	PkBitfield filter;
	gint value;
	PkBitfield values;

	/* check we can convert filter bitfield to text (none) */
	text = pk_filter_bitfield_to_string (pk_bitfield_value (PK_FILTER_ENUM_NONE));
	g_assert_cmpstr (text, ==, "none");
	g_free (text);

	/* check we can invert a bit 1 -> 0 */
	values = pk_bitfield_value (PK_FILTER_ENUM_NOT_DEVELOPMENT) | pk_bitfield_value (PK_FILTER_ENUM_NOT_NEWEST);
	pk_bitfield_invert (values, PK_FILTER_ENUM_NOT_DEVELOPMENT);
	g_assert_cmpint (values, ==, pk_bitfield_value (PK_FILTER_ENUM_NOT_NEWEST));

	/* check we can invert a bit 0 -> 1 */
	values = 0;
	pk_bitfield_invert (values, PK_FILTER_ENUM_NOT_DEVELOPMENT);
	g_assert_cmpint (values, ==, pk_bitfield_value (PK_FILTER_ENUM_NOT_DEVELOPMENT));

	/* check we can convert filter bitfield to text (single) */
	text = pk_filter_bitfield_to_string (pk_bitfield_value (PK_FILTER_ENUM_NOT_DEVELOPMENT));
	g_assert_cmpstr (text, ==, "~devel");
	g_free (text);

	/* check we can convert filter bitfield to text (plural) */
	text = pk_filter_bitfield_to_string (pk_bitfield_value (PK_FILTER_ENUM_NOT_DEVELOPMENT) |
		   pk_bitfield_value (PK_FILTER_ENUM_GUI) |
		   pk_bitfield_value (PK_FILTER_ENUM_NEWEST));
	g_assert_cmpstr (text, ==, "~devel;gui;newest");
	g_free (text);

	/* check we can convert filter text to bitfield (none) */
	filter = pk_filter_bitfield_from_string ("none");
	g_assert_cmpint (filter, ==, pk_bitfield_value (PK_FILTER_ENUM_NONE));

	/* check we can convert filter text to bitfield (single) */
	filter = pk_filter_bitfield_from_string ("~devel");
	g_assert_cmpint (filter, ==, pk_bitfield_value (PK_FILTER_ENUM_NOT_DEVELOPMENT));

	/* check we can convert filter text to bitfield (plural) */
	filter = pk_filter_bitfield_from_string ("~devel;gui;newest");
	g_assert_cmpint (filter, ==, (pk_bitfield_value (PK_FILTER_ENUM_NOT_DEVELOPMENT) |
		       pk_bitfield_value (PK_FILTER_ENUM_GUI) |
		       pk_bitfield_value (PK_FILTER_ENUM_NEWEST)));

	/* check we can add / remove bitfield */
	filter = pk_bitfield_value (PK_FILTER_ENUM_NOT_DEVELOPMENT) |
		 pk_bitfield_value (PK_FILTER_ENUM_GUI) |
		 pk_bitfield_value (PK_FILTER_ENUM_NEWEST);
	pk_bitfield_add (filter, PK_FILTER_ENUM_NOT_FREE);
	pk_bitfield_remove (filter, PK_FILTER_ENUM_NOT_DEVELOPMENT);
	text = pk_filter_bitfield_to_string (filter);
	g_assert_cmpstr (text, ==, "gui;~free;newest");
	g_free (text);

	/* check we can test enum presence */
	filter = pk_bitfield_value (PK_FILTER_ENUM_NOT_DEVELOPMENT) |
		 pk_bitfield_value (PK_FILTER_ENUM_GUI) |
		 pk_bitfield_value (PK_FILTER_ENUM_NEWEST);
	g_assert (pk_bitfield_contain (filter, PK_FILTER_ENUM_NOT_DEVELOPMENT));

	/* check we can test enum false-presence */
	g_assert (!pk_bitfield_contain (filter, PK_FILTER_ENUM_FREE));

	/* check we can add / remove bitfield to nothing */
	filter = pk_bitfield_value (PK_FILTER_ENUM_NOT_DEVELOPMENT);
	pk_bitfield_remove (filter, PK_FILTER_ENUM_NOT_DEVELOPMENT);
	text = pk_filter_bitfield_to_string (filter);
	g_assert_cmpstr (text, ==, "none");
	g_free (text);

	/* role bitfield from enums (unknown) */
	values = pk_bitfield_from_enums (PK_ROLE_ENUM_UNKNOWN, -1);
	g_assert_cmpint (values, ==, pk_bitfield_value (PK_ROLE_ENUM_UNKNOWN));

	/* role bitfield from enums (random) */
	values = pk_bitfield_from_enums (PK_ROLE_ENUM_SEARCH_GROUP, PK_ROLE_ENUM_SEARCH_DETAILS, -1);
	g_assert_cmpint (values, ==, (pk_bitfield_value (PK_ROLE_ENUM_SEARCH_DETAILS) |
		       pk_bitfield_value (PK_ROLE_ENUM_SEARCH_GROUP)));

	/* group bitfield from enums (unknown) */
	values = pk_bitfield_from_enums (PK_GROUP_ENUM_UNKNOWN, -1);
	g_assert_cmpint (values, ==, pk_bitfield_value (PK_GROUP_ENUM_UNKNOWN));

	/* group bitfield from enums (random) */
	values = pk_bitfield_from_enums (PK_GROUP_ENUM_ACCESSIBILITY, -1);
	g_assert_cmpint (values, ==, (pk_bitfield_value (PK_GROUP_ENUM_ACCESSIBILITY)));

	/* group bitfield to text (unknown) */
	values = pk_bitfield_from_enums (PK_GROUP_ENUM_UNKNOWN, -1);
	text = pk_group_bitfield_to_string (values);
	g_assert_cmpstr (text, ==, "unknown");
	g_free (text);

	/* group bitfield to text (first and last) */
	values = pk_bitfield_from_enums (PK_GROUP_ENUM_ACCESSIBILITY, PK_GROUP_ENUM_UNKNOWN, -1);
	text = pk_group_bitfield_to_string (values);
	g_assert_cmpstr (text, ==, "unknown;accessibility");
	g_free (text);

	/* group bitfield to text (random) */
	values = pk_bitfield_from_enums (PK_GROUP_ENUM_UNKNOWN, PK_GROUP_ENUM_REPOS, -1);
	text = pk_group_bitfield_to_string (values);
	g_assert_cmpstr (text, ==, "unknown;repos");
	g_free (text);

	/* priority check missing */
	values = pk_bitfield_value (PK_ROLE_ENUM_SEARCH_DETAILS) |
		 pk_bitfield_value (PK_ROLE_ENUM_SEARCH_GROUP);
	value = pk_bitfield_contain_priority (values, PK_ROLE_ENUM_SEARCH_FILE, -1);
	g_assert_cmpint (value, ==, -1);

	/* priority check first */
	value = pk_bitfield_contain_priority (values, PK_ROLE_ENUM_SEARCH_GROUP, -1);
	g_assert_cmpint (value, ==, PK_ROLE_ENUM_SEARCH_GROUP);

	/* priority check second, correct */
	value = pk_bitfield_contain_priority (values, PK_ROLE_ENUM_SEARCH_FILE, PK_ROLE_ENUM_SEARCH_GROUP, -1);
	g_assert_cmpint (value, ==, PK_ROLE_ENUM_SEARCH_GROUP);
}

gchar *_tid = NULL;

static void
pk_test_common_func (void)
{
	gchar *present;
	GDate *date;

	present = pk_get_distro_id ();
	g_assert_cmpstr (present, ==, "selftest;11.91;i686");
	g_free (present);

	/* get present iso8601 */
	present = pk_iso8601_present ();
	g_assert (present != NULL);
	g_free (present);

	/* zero length date */
	date = pk_iso8601_to_date ("");
	g_assert (date == NULL);

	/* no day specified */
	date = pk_iso8601_to_date ("2004-01");
	g_assert (date == NULL);

	/* date _and_ time specified */
	date = pk_iso8601_to_date ("2009-05-08 13:11:12");
	g_assert_cmpint (date->day, ==, 8);
	g_assert_cmpint (date->month, ==, 5);
	g_assert_cmpint (date->year, ==, 2009);
	g_date_free (date);

	/* correct date format */
	date = pk_iso8601_to_date ("2004-02-01");
	g_assert_cmpint (date->day, ==, 1);
	g_assert_cmpint (date->month, ==, 2);
	g_assert_cmpint (date->year, ==, 2004);
	g_date_free (date);
}

static void
pk_test_enum_func (void)
{
	const gchar *string;
	PkRoleEnum role_value;
	guint i;

	/* find value */
	role_value = pk_role_enum_from_string ("search-file");
	g_assert_cmpint (role_value, ==, PK_ROLE_ENUM_SEARCH_FILE);

	/* find string */
	string = pk_role_enum_to_string (PK_ROLE_ENUM_SEARCH_FILE);
	g_assert_cmpstr (string, ==, "search-file");

	/* check we convert all the role bitfield */
	for (i = 1; i < PK_ROLE_ENUM_LAST; i++) {
		string = pk_role_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the status bitfield */
	for (i = 1; i < PK_STATUS_ENUM_LAST; i++) {
		string = pk_status_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the exit bitfield */
	for (i = 0; i < PK_EXIT_ENUM_LAST; i++) {
		string = pk_exit_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the filter bitfield */
	for (i = 0; i < PK_FILTER_ENUM_LAST; i++) {
		string = pk_filter_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the restart bitfield */
	for (i = 0; i < PK_RESTART_ENUM_LAST; i++) {
		string = pk_restart_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the error_code bitfield */
	for (i = 0; i < PK_ERROR_ENUM_LAST; i++) {
		string = pk_error_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the group bitfield */
	for (i = 1; i < PK_GROUP_ENUM_LAST; i++) {
		string = pk_group_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the info bitfield */
	for (i = 1; i < PK_INFO_ENUM_LAST; i++) {
		string = pk_info_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the sig_type bitfield */
	for (i = 0; i < PK_SIGTYPE_ENUM_LAST; i++) {
		string = pk_sig_type_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the upgrade bitfield */
	for (i = 0; i < PK_DISTRO_UPGRADE_ENUM_LAST; i++) {
		string = pk_distro_upgrade_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}

	/* check we convert all the media type bitfield */
	for (i = 0; i < PK_MEDIA_TYPE_ENUM_LAST; i++) {
		string = pk_media_type_enum_to_string (i);
		if (string == NULL) {
			/* so we get the value of i in the assert text */
			g_assert_cmpint (0, ==, i);
			break;
		}
	}
}

static void
pk_test_package_id_func (void)
{
	gboolean ret;
	gchar *text;
	gchar **sections;

	/* check not valid - NULL */
	ret = pk_package_id_check (NULL);
	g_assert (!ret);

	/* check not valid - no name */
	ret = pk_package_id_check (";0.0.1;i386;fedora");
	g_assert (!ret);

	/* check not valid - invalid */
	ret = pk_package_id_check ("moo;0.0.1;i386");
	g_assert (!ret);

	/* check valid */
	ret = pk_package_id_check ("moo;0.0.1;i386;fedora");
	g_assert (ret);

	/* id build */
	text = pk_package_id_build ("moo", "0.0.1", "i386", "fedora");
	g_assert_cmpstr (text, ==, "moo;0.0.1;i386;fedora");
	g_free (text);

	/* id build partial */
	text = pk_package_id_build ("moo", NULL, NULL, NULL);
	g_assert_cmpstr (text, ==, "moo;;;");
	g_free (text);

	/* test printable */
	text = pk_package_id_to_printable ("moo;0.0.1;i386;fedora");
	g_assert_cmpstr (text, ==, "moo-0.0.1.i386");
	g_free (text);

	/* test printable no arch */
	text = pk_package_id_to_printable ("moo;0.0.1;;");
	g_assert_cmpstr (text, ==, "moo-0.0.1");
	g_free (text);

	/* test printable just name */
	text = pk_package_id_to_printable ("moo;;;");
	g_assert_cmpstr (text, ==, "moo");
	g_free (text);

	/* test on real packageid */
	sections = pk_package_id_split ("kde-i18n-csb;4:3.5.8~pre20071001-0ubuntu1;all;");
	g_assert (sections != NULL);
	g_assert_cmpstr (sections[0], ==, "kde-i18n-csb");
	g_assert_cmpstr (sections[1], ==, "4:3.5.8~pre20071001-0ubuntu1");
	g_assert_cmpstr (sections[2], ==, "all");
	g_assert_cmpstr (sections[3], ==, "");
	g_strfreev (sections);

	/* test on short packageid */
	sections = pk_package_id_split ("kde-i18n-csb;4:3.5.8~pre20071001-0ubuntu1;;");
	g_assert (sections != NULL);
	g_assert_cmpstr (sections[0], ==, "kde-i18n-csb");
	g_assert_cmpstr (sections[1], ==, "4:3.5.8~pre20071001-0ubuntu1");
	g_assert_cmpstr (sections[2], ==, "");
	g_assert_cmpstr (sections[3], ==, "");
	g_strfreev (sections);

	/* test fail under */
	sections = pk_package_id_split ("foo;moo");
	g_assert (sections == NULL);

	/* test fail over */
	sections = pk_package_id_split ("foo;moo;dave;clive;dan");
	g_assert (sections == NULL);

	/* test fail missing first */
	sections = pk_package_id_split (";0.1.2;i386;data");
	g_assert (sections == NULL);
}

static void
pk_test_package_ids_func (void)
{
	gboolean ret;
	gchar *package_ids_blank[] = {NULL};
	gchar **package_ids;

	/* parse va_list */
	package_ids = pk_package_ids_from_string ("foo;0.0.1;i386;fedora&bar;0.1.1;noarch;livna");
	g_assert (package_ids != NULL);

	/* verify size */
	g_assert_cmpint (g_strv_length (package_ids), ==, 2);

	/* verify blank */
	ret = pk_package_ids_check (package_ids_blank);
	g_assert (!ret);

	/* verify */
	ret = pk_package_ids_check (package_ids);
	g_assert (ret);

	g_strfreev (package_ids);
}

static void
pk_test_progress_func (void)
{
	PkProgress *progress;

	progress = pk_progress_new ();
	g_assert (progress != NULL);

	g_object_unref (progress);
}

static void
pk_test_progress_bar (void)
{
	PkProgressBar *progress_bar;

	progress_bar = pk_progress_bar_new ();
	g_assert (progress_bar != NULL);

	g_object_unref (progress_bar);
}

static void
pk_test_results_func (void)
{
	gboolean ret;
	PkResults *results;
	PkExitEnum exit_enum;
	GPtrArray *packages;
	PkPackage *item;
	PkInfoEnum info;
	gchar *package_id;
	gchar *summary;
	GError *error = NULL;

	/* get results */
	results = pk_results_new ();
	g_assert (results != NULL);

	/* get exit code of unset results */
	exit_enum = pk_results_get_exit_code (results);
	g_assert_cmpint (exit_enum, ==, PK_EXIT_ENUM_UNKNOWN);

	/* get package list of unset results */
	packages = pk_results_get_package_array (results);
	g_assert_cmpint (packages->len, ==, 0);
	g_ptr_array_unref (packages);

	/* set valid exit code */
	ret = pk_results_set_exit_code (results, PK_EXIT_ENUM_CANCELLED);
	g_assert (ret);

	/* get exit code of set results */
	exit_enum = pk_results_get_exit_code (results);
	g_assert_cmpint (exit_enum, ==, PK_EXIT_ENUM_CANCELLED);

	/* add package */
	item = pk_package_new ();
	g_object_set (item,
		      "info", PK_INFO_ENUM_AVAILABLE,
		      "summary", "Power manager for GNOME",
		      NULL);
	ret = pk_package_set_id (item,
				 "gnome-power-manager;0.1.2;i386;fedora",
				 &error);
	g_assert_no_error (error);
	g_assert (ret);
	ret = pk_results_add_package (results, item);
	g_object_unref (item);
	g_assert (ret);

	/* get package list of set results */
	packages = pk_results_get_package_array (results);
	g_assert_cmpint (packages->len, ==, 1);

	/* check data */
	item = g_ptr_array_index (packages, 0);
	g_object_get (item,
		      "info", &info,
		      "package-id", &package_id,
		      "summary", &summary,
		      NULL);
	g_assert_cmpint (info, ==, PK_INFO_ENUM_AVAILABLE);
	g_assert_cmpstr ("gnome-power-manager;0.1.2;i386;fedora", ==, package_id);
	g_assert_cmpstr ("Power manager for GNOME", ==, summary);
	g_object_ref (item);
	g_ptr_array_unref (packages);
	g_free (package_id);
	g_free (summary);

	/* check ref */
	g_object_get (item,
		      "info", &info,
		      "package-id", &package_id,
		      "summary", &summary,
		      NULL);
	g_assert_cmpint (info, ==, PK_INFO_ENUM_AVAILABLE);
	g_assert_cmpstr ("gnome-power-manager;0.1.2;i386;fedora", ==, package_id);
	g_assert_cmpstr ("Power manager for GNOME", ==, summary);
	g_object_unref (item);
	g_free (package_id);
	g_free (summary);

	g_object_unref (results);
}

static void
pk_test_package_func (void)
{
	gboolean ret;
	PkPackage *package;
	const gchar *id;
	gchar *text;
	GError *error = NULL;

	/* get package */
	package = pk_package_new ();
	g_assert (package != NULL);

	/* get id of unset package */
	id = pk_package_get_id (package);
	g_assert_cmpstr (id, ==, NULL);

	/* get id of unset package */
	g_object_get (package, "package-id", &text, NULL);
	g_assert_cmpstr (text, ==, NULL);
	g_free (text);

	/* set invalid id */
	ret = pk_package_set_id (package, "gnome-power-manager", &error);
	g_assert_error (error, 1, 0);
	g_assert (!ret);
	g_clear_error (&error);

	/* set invalid id (sections) */
	ret = pk_package_set_id (package, "gnome-power-manager;0.1.2;i386", &error);
	g_assert_error (error, 1, 0);
	g_assert (!ret);
	g_clear_error (&error);

	/* set invalid id (sections) */
	ret = pk_package_set_id (package, "gnome-power-manager;0.1.2;i386;fedora;dave", &error);
	g_assert_error (error, 1, 0);
	g_assert (!ret);
	g_clear_error (&error);

	/* set invalid name */
	ret = pk_package_set_id (package, ";0.1.2;i386;fedora", &error);
	g_assert_error (error, 1, 0);
	g_assert (!ret);
	g_clear_error (&error);

	/* set valid name */
	ret = pk_package_set_id (package, "gnome-power-manager;0.1.2;i386;fedora", &error);
	g_assert_no_error (error);
	g_assert (ret);

	/* get id of set package */
	id = pk_package_get_id (package);
	g_assert_cmpstr (id, ==, "gnome-power-manager;0.1.2;i386;fedora");

	/* get name of set package */
	g_object_get (package, "package-id", &text, NULL);
	g_assert_cmpstr (text, ==, "gnome-power-manager;0.1.2;i386;fedora");
	g_free (text);

	g_object_unref (package);
}

int
main (int argc, char **argv)
{
#if (GLIB_MAJOR_VERSION == 2 && GLIB_MINOR_VERSION < 35)
	g_type_init ();
#endif

	g_test_init (&argc, &argv, NULL);

	pk_debug_set_verbose (TRUE);
	pk_debug_add_log_domain (G_LOG_DOMAIN);

	/* some libraries need to know */
	g_setenv ("PK_SELF_TEST", "1", TRUE);

	/* tests go here */
	g_test_add_func ("/packagekit-glib2/common", pk_test_common_func);
	g_test_add_func ("/packagekit-glib2/enum", pk_test_enum_func);
	g_test_add_func ("/packagekit-glib2/bitfield", pk_test_bitfield_func);
	g_test_add_func ("/packagekit-glib2/package-id", pk_test_package_id_func);
	g_test_add_func ("/packagekit-glib2/package-ids", pk_test_package_ids_func);
	g_test_add_func ("/packagekit-glib2/progress", pk_test_progress_func);
	g_test_add_func ("/packagekit-glib2/results", pk_test_results_func);
	g_test_add_func ("/packagekit-glib2/package", pk_test_package_func);
	g_test_add_func ("/packagekit-glib2/progress-bar", pk_test_progress_bar);

	return g_test_run ();
}

