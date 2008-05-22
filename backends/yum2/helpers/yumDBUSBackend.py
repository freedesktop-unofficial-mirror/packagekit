#!/usr/bin/python
# Licensed under the GNU General Public License Version 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.

# Copyright (C) 2007
#    Tim Lauridsen <timlau@fedoraproject.org>
#    Seth Vidal <skvidal@fedoraproject.org>
#    Luke Macken <lmacken@redhat.com>
#    James Bowes <jbowes@dangerouslyinc.com>
#    Robin Norwood <rnorwood@redhat.com>

# imports

import re

from packagekit.daemonBackend import PackageKitBaseBackend
from packagekit.daemonBackend import threaded, async
from packagekit.daemonBackend import pklog

# This is common between backends
from packagekit.daemonBackend import PACKAGEKIT_DBUS_INTERFACE, PACKAGEKIT_DBUS_PATH

from packagekit.enums import *
from packagekit.daemonBackend import PackagekitProgress
import yum
from urlgrabber.progress import BaseMeter,format_time,format_number
import urlgrabber
from yum.rpmtrans import RPMBaseCallback
from yum.constants import *
from yum.update_md import UpdateMetadata
from yum.callbacks import *
from yum.misc import prco_tuple_to_string, unique, keyInstalled, procgpgkey, getgpgkeyinfo, keyIdToRPMVer

import dbus
import dbus.service
import dbus.mainloop.glib

import rpmUtils
import exceptions
import types
import signal
import time
import os.path
import operator
import threading
import gobject
import dbus
import dbus.glib
import dbus.service
import dbus.mainloop.glib


# Global vars
yumbase = None
progress = PackagekitProgress()  # Progress object to store the progress

groupMap = {
'desktops;gnome-desktop'                      : GROUP_DESKTOP_GNOME,
'desktops;window-managers'                    : GROUP_DESKTOP_OTHER,
'desktops;kde-desktop'                        : GROUP_DESKTOP_KDE,
'desktops;xfce-desktop'                       : GROUP_DESKTOP_XFCE,
'apps;authoring-and-publishing'               : GROUP_PUBLISHING,
'apps;office'                                 : GROUP_OFFICE,
'apps;sound-and-video'                        : GROUP_MULTIMEDIA,
'apps;editors'                                : GROUP_OFFICE,
'apps;engineering-and-scientific'             : GROUP_OTHER,
'apps;games'                                  : GROUP_GAMES,
'apps;graphics'                               : GROUP_GRAPHICS,
'apps;text-internet'                          : GROUP_INTERNET,
'apps;graphical-internet'                     : GROUP_INTERNET,
'apps;education'                              : GROUP_EDUCATION,
'development;kde-software-development'        : GROUP_PROGRAMMING,
'development;gnome-software-development'      : GROUP_PROGRAMMING,
'development;development-tools'               : GROUP_PROGRAMMING,
'development;eclipse'                         : GROUP_PROGRAMMING,
'development;development-libs'                : GROUP_PROGRAMMING,
'development;x-software-development'          : GROUP_PROGRAMMING,
'development;web-development'                 : GROUP_PROGRAMMING,
'development;legacy-software-development'     : GROUP_PROGRAMMING,
'development;ruby'                            : GROUP_PROGRAMMING,
'development;java-development'                : GROUP_PROGRAMMING,
'development;xfce-software-development'       : GROUP_PROGRAMMING,
'servers;clustering'                          : GROUP_SERVERS,
'servers;dns-server'                          : GROUP_SERVERS,
'servers;server-cfg'                          : GROUP_SERVERS,
'servers;news-server'                         : GROUP_SERVERS,
'servers;web-server'                          : GROUP_SERVERS,
'servers;smb-server'                          : GROUP_SERVERS,
'servers;sql-server'                          : GROUP_SERVERS,
'servers;ftp-server'                          : GROUP_SERVERS,
'servers;printing'                            : GROUP_SERVERS,
'servers;mysql'                               : GROUP_SERVERS,
'servers;mail-server'                         : GROUP_SERVERS,
'servers;network-server'                      : GROUP_SERVERS,
'servers;legacy-network-server'               : GROUP_SERVERS,
'base-system;java'                            : GROUP_SYSTEM,
'base-system;base-x'                          : GROUP_SYSTEM,
'base-system;system-tools'                    : GROUP_ADMIN_TOOLS,
'base-system;fonts'                           : GROUP_FONTS,
'base-system;hardware-support'                : GROUP_SYSTEM,
'base-system;dial-up'                         : GROUP_SYSTEM,
'base-system;admin-tools'                     : GROUP_ADMIN_TOOLS,
'base-system;legacy-software-support'         : GROUP_LEGACY,
'base-system;base'                            : GROUP_SYSTEM,
'base-system;virtualization'                  : GROUP_VIRTUALIZATION,
'base-system;legacy-fonts'                    : GROUP_FONTS,
'language-support;khmer-support'              : GROUP_LOCALIZATION,
'language-support;persian-support'            : GROUP_LOCALIZATION,
'language-support;georgian-support'           : GROUP_LOCALIZATION,
'language-support;malay-support'              : GROUP_LOCALIZATION,
'language-support;tonga-support'              : GROUP_LOCALIZATION,
'language-support;portuguese-support'         : GROUP_LOCALIZATION,
'language-support;japanese-support'           : GROUP_LOCALIZATION,
'language-support;hungarian-support'          : GROUP_LOCALIZATION,
'language-support;somali-support'             : GROUP_LOCALIZATION,
'language-support;punjabi-support'            : GROUP_LOCALIZATION,
'language-support;bhutanese-support'          : GROUP_LOCALIZATION,
'language-support;british-support'            : GROUP_LOCALIZATION,
'language-support;korean-support'             : GROUP_LOCALIZATION,
'language-support;lao-support'                : GROUP_LOCALIZATION,
'language-support;inuktitut-support'          : GROUP_LOCALIZATION,
'language-support;german-support'             : GROUP_LOCALIZATION,
'language-support;hindi-support'              : GROUP_LOCALIZATION,
'language-support;faeroese-support'           : GROUP_LOCALIZATION,
'language-support;swedish-support'            : GROUP_LOCALIZATION,
'language-support;tsonga-support'             : GROUP_LOCALIZATION,
'language-support;russian-support'            : GROUP_LOCALIZATION,
'language-support;serbian-support'            : GROUP_LOCALIZATION,
'language-support;latvian-support'            : GROUP_LOCALIZATION,
'language-support;samoan-support'             : GROUP_LOCALIZATION,
'language-support;sinhala-support'            : GROUP_LOCALIZATION,
'language-support;catalan-support'            : GROUP_LOCALIZATION,
'language-support;lithuanian-support'         : GROUP_LOCALIZATION,
'language-support;turkish-support'            : GROUP_LOCALIZATION,
'language-support;arabic-support'             : GROUP_LOCALIZATION,
'language-support;vietnamese-support'         : GROUP_LOCALIZATION,
'language-support;mongolian-support'          : GROUP_LOCALIZATION,
'language-support;tswana-support'             : GROUP_LOCALIZATION,
'language-support;irish-support'              : GROUP_LOCALIZATION,
'language-support;italian-support'            : GROUP_LOCALIZATION,
'language-support;slovak-support'             : GROUP_LOCALIZATION,
'language-support;slovenian-support'          : GROUP_LOCALIZATION,
'language-support;belarusian-support'         : GROUP_LOCALIZATION,
'language-support;northern-sotho-support'     : GROUP_LOCALIZATION,
'language-support;kannada-support'            : GROUP_LOCALIZATION,
'language-support;malayalam-support'          : GROUP_LOCALIZATION,
'language-support;swati-support'              : GROUP_LOCALIZATION,
'language-support;breton-support'             : GROUP_LOCALIZATION,
'language-support;romanian-support'           : GROUP_LOCALIZATION,
'language-support;greek-support'              : GROUP_LOCALIZATION,
'language-support;tagalog-support'            : GROUP_LOCALIZATION,
'language-support;zulu-support'               : GROUP_LOCALIZATION,
'language-support;tibetan-support'            : GROUP_LOCALIZATION,
'language-support;danish-support'             : GROUP_LOCALIZATION,
'language-support;afrikaans-support'          : GROUP_LOCALIZATION,
'language-support;southern-sotho-support'     : GROUP_LOCALIZATION,
'language-support;bosnian-support'            : GROUP_LOCALIZATION,
'language-support;brazilian-support'          : GROUP_LOCALIZATION,
'language-support;basque-support'             : GROUP_LOCALIZATION,
'language-support;welsh-support'              : GROUP_LOCALIZATION,
'language-support;thai-support'               : GROUP_LOCALIZATION,
'language-support;telugu-support'             : GROUP_LOCALIZATION,
'language-support;low-saxon-support'          : GROUP_LOCALIZATION,
'language-support;urdu-support'               : GROUP_LOCALIZATION,
'language-support;tamil-support'              : GROUP_LOCALIZATION,
'language-support;indonesian-support'         : GROUP_LOCALIZATION,
'language-support;gujarati-support'           : GROUP_LOCALIZATION,
'language-support;xhosa-support'              : GROUP_LOCALIZATION,
'language-support;chinese-support'            : GROUP_LOCALIZATION,
'language-support;czech-support'              : GROUP_LOCALIZATION,
'language-support;venda-support'              : GROUP_LOCALIZATION,
'language-support;bulgarian-support'          : GROUP_LOCALIZATION,
'language-support;albanian-support'           : GROUP_LOCALIZATION,
'language-support;galician-support'           : GROUP_LOCALIZATION,
'language-support;armenian-support'           : GROUP_LOCALIZATION,
'language-support;dutch-support'              : GROUP_LOCALIZATION,
'language-support;oriya-support'              : GROUP_LOCALIZATION,
'language-support;maori-support'              : GROUP_LOCALIZATION,
'language-support;nepali-support'             : GROUP_LOCALIZATION,
'language-support;icelandic-support'          : GROUP_LOCALIZATION,
'language-support;ukrainian-support'          : GROUP_LOCALIZATION,
'language-support;assamese-support'           : GROUP_LOCALIZATION,
'language-support;bengali-support'            : GROUP_LOCALIZATION,
'language-support;spanish-support'            : GROUP_LOCALIZATION,
'language-support;hebrew-support'             : GROUP_LOCALIZATION,
'language-support;estonian-support'           : GROUP_LOCALIZATION,
'language-support;french-support'             : GROUP_LOCALIZATION,
'language-support;croatian-support'           : GROUP_LOCALIZATION,
'language-support;filipino-support'           : GROUP_LOCALIZATION,
'language-support;finnish-support'            : GROUP_LOCALIZATION,
'language-support;norwegian-support'          : GROUP_LOCALIZATION,
'language-support;southern-ndebele-support'   : GROUP_LOCALIZATION,
'language-support;polish-support'             : GROUP_LOCALIZATION,
'language-support;gaelic-support'             : GROUP_LOCALIZATION,
'language-support;marathi-support'            : GROUP_LOCALIZATION,
'language-support;ethiopic-support'           : GROUP_LOCALIZATION
}

MetaDataMap = {
    'repomd'        : STATUS_DOWNLOAD_REPOSITORY,
    'primary'       : STATUS_DOWNLOAD_PACKAGELIST,
    'filelists'     : STATUS_DOWNLOAD_FILELIST,
    'other'         : STATUS_DOWNLOAD_CHANGELOG,
    'comps'         : STATUS_DOWNLOAD_GROUP,
    'updateinfo'    : STATUS_DOWNLOAD_UPDATEINFO
}

GUI_KEYS = re.compile(r'(qt)|(gtk)')

class GPGKeyNotImported(exceptions.Exception):
    pass

def sigquit(signum, frame):
    print >> sys.stderr, "Quit signal sent - exiting immediately"
    if yumbase:
        print >> sys.stderr, "unlocking Yum"
        yumbase.closeRpmDB()
        yumbase.doUnlock(YUM_PID_FILE)
    sys.exit(1)

# This is specific to this backend
PACKAGEKIT_DBUS_SERVICE = 'org.freedesktop.PackageKitYumBackend'

# Setup threading support
gobject.threads_init()
dbus.glib.threads_init()

class PackageKitYumBackend(PackageKitBaseBackend):

    # Packages there require a reboot
    rebootpkgs = ("kernel", "kernel-smp", "kernel-xen-hypervisor", "kernel-PAE",
              "kernel-xen0", "kernel-xenU", "kernel-xen", "kernel-xen-guest",
              "glibc", "hal", "dbus", "xen")

    def __init__(self, bus_name, dbus_path):
        signal.signal(signal.SIGQUIT, sigquit)

        print "__init__"
        self.locked = False
        self._cancelled = threading.Event()
        self._cancelled.clear()
        self._lock = threading.Lock()

        PackageKitBaseBackend.__init__(self,
                                       bus_name,
                                       dbus_path)

        print "__init__ done"

#
# Signals ( backend -> engine -> client )
#

    #FIXME: _show_description and _show_package wrap Description and
    #       Package so that the encoding can be fixed. This is ugly.
    #       we could probably use a decorator to do it instead.

    def _show_package(self,pkg,status):
        '''
        send 'package' signal
        @param info: the enumerated INFO_* string
        @param id: The package ID name, e.g. openoffice-clipart;2.6.22;ppc64;fedora
        @param summary: The package Summary
        convert the summary to UTF before sending
        '''
        id = self._pkg_to_id(pkg)
        summary = self._to_unicode(pkg.summary)
        self.Package(status,id,summary)

    def _show_description(self,id,license,group,desc,url,bytes):
        '''
        Send 'description' signal
        @param id: The package ID name, e.g. openoffice-clipart;2.6.22;ppc64;fedora
        @param license: The license of the package
        @param group: The enumerated group
        @param desc: The multi line package description
        @param url: The upstream project homepage
        @param bytes: The size of the package, in bytes
        convert the description to UTF before sending
        '''
        desc = self._to_unicode(desc)
        self.Description(id,license,group,desc,url,bytes)

    def _show_update_detail(self,pkg,update,obsolete,vendor_url,bz_url,cve_url,reboot,desc):
        '''
        Send the 'UpdateDetail' signal
        convert the description to UTF before sending
        '''
        id = self._pkg_to_id(pkg)
        desc = self._to_unicode(desc)
        self.UpdateDetail(id,update,obsolete,vendor_url,bz_url,cve_url,reboot,desc)

#
# Utility methods for Signals
#

    def _to_unicode(self, txt, encoding='utf-8'):
        if isinstance(txt, basestring):
            if not isinstance(txt, unicode):
                txt = unicode(txt, encoding, errors='replace')
        return txt

    def _pkg_to_id(self,pkg):
        pkgver = self._get_package_ver(pkg)
        id = self._get_package_id(pkg.name, pkgver, pkg.arch, pkg.repo)
        return id

#
# Methods ( client -> engine -> backend )
#

    @threaded
    @async
    def doInit(self):
        print "Now in doInit()"
        # yumbase is defined outside of this class so the sigquit handler can close the DB.
        yumbase = PackageKitYumBase(self)
        self.yumbase = yumbase
        print "new yumbase object"
        self._setup_yum()
        print "yum set up"

    @threaded
    @async
    def doExit(self):
        if self.locked:
            self._unlock_yum()

    def _lock_yum(self):
        ''' Lock Yum'''
        retries = 0
        while not self.locked:
            try: # Try to lock yum
                self.yumbase.doLock( YUM_PID_FILE )
                self.locked = True
            except:
                time.sleep(2)
                retries += 1
                if retries > 20:
                    self.ErrorCode(ERROR_CANNOT_GET_LOCK,'Yum is locked by another application')
                    self.Finished(EXIT_FAILED)
                    self.loop.quit()

    def _unlock_yum(self):
        ''' Unlock Yum'''
        if self.locked:
            self.yumbase.closeRpmDB()
            self.yumbase.doUnlock(YUM_PID_FILE)

    def doCancel(self):
        pklog.info("Canceling current action")
        self.StatusChanged(STATUS_CANCEL)
        self._cancelled.set()
        self._cancelled.wait()

    def _cancel_check(self, msg):
        if self._cancelled.isSet():
            self._unlock_yum()
            self.ErrorCode(ERROR_TRANSACTION_CANCELLED, msg)
            self.Finished(EXIT_KILL)
            self._cancelled.clear()
            return True
        return False
        
    @threaded
    @async
    def doSearchName(self, filters, search):
        '''
        Implement the {backend}-search-name functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()

        searchlist = ['name']
        self.StatusChanged(STATUS_QUERY)

        successful = self._do_search(searchlist, filters, search)
        if not successful:
            # _do_search unlocks yum, sets errors, and calls Finished() if it fails.
            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doSearchDetails(self,filters,key):
        '''
        Implement the {backend}-search-details functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()

        searchlist = ['name', 'summary', 'description', 'group']
        self.StatusChanged(STATUS_QUERY)

        successful = self._do_search(searchlist, filters, key)
        if not successful:
            # _do_search unlocks yum, sets errors, and calls Finished() if it fails.
            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doSearchGroup(self,filters,key):
        '''
        Implement the {backend}-search-group functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_QUERY)

        try:
            pkgGroupDict = self._buildGroupDict()
            fltlist = filters.split(';')
            found = {}

            if not FILTER_NOT_INSTALLED in fltlist:
                # Check installed for group
                for pkg in self.yumbase.rpmdb:
                    if self._cancel_check("Search cancelled."):
                        # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                        return

                    group = GROUP_OTHER                    # Default Group
                    if pkgGroupDict.has_key(pkg.name):     # check if pkg name exist in package / group dictinary
                        cg = pkgGroupDict[pkg.name]
                        if groupMap.has_key(cg):
                            group = groupMap[cg]           # use the pk group name, instead of yum 'category/group'
                    if group == key:
                        if self._do_extra_filtering(pkg, fltlist):
                            self._show_package(pkg, INFO_INSTALLED)
            if not FILTER_INSTALLED in fltlist:
                # Check available for group
                for pkg in self.yumbase.pkgSack:
                    if self._cancel_check("Search cancelled."):
                        # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                        return
                    group = GROUP_OTHER
                    if pkgGroupDict.has_key(pkg.name):
                        cg = pkgGroupDict[pkg.name]
                        if groupMap.has_key(cg):
                            group = groupMap[cg]
                    if group == key:
                        if self._do_extra_filtering(pkg, fltlist):
                            self._show_package(pkg, INFO_AVAILABLE)
        except yum.Errors.RepoError,e:
            self.Message(MESSAGE_NOTICE, "The package cache is invalid and is being rebuilt.")
            self._refresh_yum_cache()
            self._unlock_yum()
            self.Finished(EXIT_FAILED)

            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doSearchFile(self,filters,key):
        '''
        Implement the {backend}-search-file functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_QUERY)

        try:
            fltlist = filters.split(';')
            found = {}
            if not FILTER_NOT_INSTALLED in fltlist:
                # Check installed for file
                matches = self.yumbase.rpmdb.searchFiles(key)
                for pkg in matches:
                    if self._cancel_check("Search cancelled."):
                        # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                        return
                    if not found.has_key(str(pkg)):
                        if self._do_extra_filtering(pkg, fltlist):
                            self._show_package(pkg, INFO_INSTALLED)
                            found[str(pkg)] = 1
            if not FILTER_INSTALLED in fltlist:
                # Check available for file
                self.yumbase.repos.populateSack(mdtype='filelists')
                matches = self.yumbase.pkgSack.searchFiles(key)
                for pkg in matches:
                    if self._cancel_check("Search cancelled."):
                        # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                        return
                    if found.has_key(str(pkg)):
                        if self._do_extra_filtering(pkg, fltlist):
                            self._show_package(pkg, INFO_AVAILABLE)
                            found[str(pkg)] = 1
        except yum.Errors.RepoError,e:
            self.Message(MESSAGE_NOTICE, "The package cache is invalid and is being rebuilt.")
            self._refresh_yum_cache()
            self._unlock_yum()
            self.Finished(EXIT_FAILED)

            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doGetRequires(self,filters,package,recursive):
        '''
        Print a list of requires for a given package
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_INFO)
        pkg,inst = self._findPackage(package)

        if not pkg:
            self._unlock_yum()
            self.ErrorCode(ERROR_PACKAGE_NOT_FOUND,'Package was not found')
            self.Finished(EXIT_FAILED)
            return

        if self._cancel_check("Search cancelled."):
            # _cancel_check() sets the error message, unlocks yum, and calls Finished()
            return

        fltlist = filters.split(';')

        if not FILTER_NOT_INSTALLED in fltlist:
            results = self.yumbase.pkgSack.searchRequires(pkg.name)
            for result in results:
                if self._cancel_check("Search cancelled."):
                    # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                    return

                self._show_package(result,INFO_AVAILABLE)

        if not FILTER_INSTALLED in fltlist:
            results = self.yumbase.rpmdb.searchRequires(pkg.name)
            for result in results:
                if self._cancel_check("Search cancelled."):
                    # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                    return
                self._show_package(result,INFO_INSTALLED)

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doGetDepends(self,package,recursive):
        '''
        Print a list of depends for a given package
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.PercentageChanged(0)
        self.StatusChanged(STATUS_INFO)

        name = package.split(';')[0]
        pkg,inst = self._findPackage(package)
        results = {}

        if not pkg:
            self._unlock_yum()
            self.ErrorCode(ERROR_PACKAGE_NOT_FOUND,'Package was not found')
            self.Finished(EXIT_FAILED)
            return

        if self._cancel_check("Search cancelled."):
            # _cancel_check() sets the error message, unlocks yum, and calls Finished()
            return

        (dep_resolution_errors, deps) = self._get_best_dependencies(pkg)

        if len(dep_resolution_errors) > 0:
            self.ErrorCode(ERROR_DEP_RESOLUTION_FAILED,
                           "Could not resolve dependencies: (" +
                           ", ".join(dep_resolution_errors) +
                           ")")

            self._unlock_yum()
            self.Finished(EXIT_FAILED)
            return

        for pkg in deps:
            if self._cancel_check("Search cancelled."):
                # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                return

            if pkg.name != name:
                pkgver = self._get_package_ver(pkg)
                id = self._get_package_id(pkg.name, pkgver, pkg.arch, pkg.repoid)

                if self._is_inst(pkg):
                    self._show_package(pkg, INFO_INSTALLED)
                else:
                    if self._installable(pkg):
                        self._show_package(pkg, INFO_AVAILABLE)

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doUpdateSystem(self):
        '''
        Implement the {backend}-update-system functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(False)
        self.PercentageChanged(0)
        self.StatusChanged(STATUS_RUNNING)
        old_throttle = self.yumbase.conf.throttle
        self.yumbase.conf.throttle = "60%" # Set bandwidth throttle to 60%
                                           # to avoid taking all the system's bandwidth.
        old_skip_broken = self.yumbase.conf.skip_broken
        self.yumbase.conf.skip_broken = 1
        self.yumbase.skipped_packages = []

        txmbr = self.yumbase.update() # Add all updates to Transaction
        if txmbr:
            successful = self._runYumTransaction()
            skipped_packages = self.yumbase.skipped_packages
            self.yumbase.skipped_packages = []
            if not successful:
                self.yumbase.conf.throttle = old_throttle
                self.yumbase.conf.skip_broken = old_skip_broken
                # _runYumTransaction() sets the error code and calls Finished()
                return
            # Transaction successful, but maybe some packages were skipped.
            for package in skipped_packages:
                self._show_package(package, INFO_BLOCKED)
        else:
            self.yumbase.conf.throttle = old_throttle
            self.yumbase.conf.skip_broken = old_skip_broken
            self._unlock_yum()
            self.ErrorCode(ERROR_NO_PACKAGES_TO_UPDATE,"Nothing to do")
            self.Finished(EXIT_FAILED)
            return

        self.yumbase.conf.throttle = old_throttle
        self.yumbase.conf.skip_broken = old_skip_broken
        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doRefreshCache(self, force):
        '''
        Implement the {backend}-refresh_cache functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.PercentageChanged(0)
        self.StatusChanged(STATUS_REFRESH_CACHE)

        old_cache_setting = self.yumbase.conf.cache
        self.yumbase.conf.cache = 0
        self.yumbase.repos.setCache(0)

        pct = 0
        try:
            if len(self.yumbase.repos.listEnabled()) == 0:
                self.PercentageChanged(100)
                self._unlock_yum()
                self.Finished(EXIT_SUCCESS)
                return

            #work out the slice for each one
            bump = (95/len(self.yumbase.repos.listEnabled()))/2

            for repo in self.yumbase.repos.listEnabled():
                repo.metadata_expire = 0
                self.yumbase.repos.populateSack(which=[repo.id], mdtype='metadata', cacheonly=1)
                if self._cancel_check("Action cancelled."):
                    # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                    return
                pct+=bump
                self.PercentageChanged(pct)
                self.yumbase.repos.populateSack(which=[repo.id], mdtype='filelists', cacheonly=1)
                if self._cancel_check("Action cancelled."):
                    # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                    return
                pct+=bump
                self.PercentageChanged(pct)
                self.yumbase.repos.populateSack(which=[repo.id], mdtype='otherdata', cacheonly=1)
                if self._cancel_check("Action cancelled."):
                    # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                    return
                pct+=bump
                self.PercentageChanged(pct)

            self.PercentageChanged(95)
            # Setup categories/groups
            self.yumbase.doGroupSetup()
            #we might have a rounding error
            self.PercentageChanged(100)

        except yum.Errors.YumBaseError, e:
            self._unlock_yum()
            # This should be a better-defined error, but I'm not sure
            # what the exceptions yum is likely to throw here are.
            self.ErrorCode(ERROR_UNKNOWN,str(e))
            self.Finished(EXIT_FAILED)
            self.Exit()

        self.yumbase.conf.cache = old_cache_setting
        self.yumbase.repos.setCache(old_cache_setting)

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doResolve(self, filters, name):
        '''
        Implement the {backend}-resolve functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_QUERY)

        fltlist = filters.split(';')
        try:
            # Get installed packages
            installedByKey = self.yumbase.rpmdb.searchNevra(name=name)
            if FILTER_NOT_INSTALLED not in fltlist:
                for pkg in installedByKey:
                    if self._cancel_check("Search cancelled."):
                        # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                        return

                    self._show_package(pkg,INFO_INSTALLED)
            # Get available packages
            if FILTER_INSTALLED not in fltlist:
                for pkg in self.yumbase.pkgSack.returnNewestByNameArch():
                    if self._cancel_check("Search cancelled."):
                        # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                        return
                    if pkg.name == name:
                        show = True
                        for instpo in installedByKey:
                            # Check if package have a smaller & equal EVR to a inst pkg
                            if pkg.EVR < instpo.EVR or pkg.EVR == instpo.EVR:
                                show = False
                        if show:
                            self._show_package(pkg,INFO_AVAILABLE)
                            break
        except yum.Errors.RepoError,e:
            self.Message(MESSAGE_NOTICE, "The package cache is invalid and is being rebuilt.")
            self._refresh_yum_cache()
            self._unlock_yum()
            self.Finished(EXIT_FAILED)

            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doInstallPackage(self, package):
        '''
        Implement the {backend}-install functionality
        This will only work with yum 3.2.4 or higher
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(False)
        self.PercentageChanged(0)
        self.StatusChanged(STATUS_RUNNING)

        pkg,inst = self._findPackage(package)
        if pkg:
            if inst:
                self._unlock_yum()
                self.ErrorCode(ERROR_PACKAGE_ALREADY_INSTALLED,'Package already installed')
                self.Finished(EXIT_FAILED)
                return
            try:
                txmbr = self.yumbase.install(name=pkg.name)
                successful = self._runYumTransaction()
                if not successful:
                    # _runYumTransaction unlocked yum, set the error code, and called Finished.
                    return
            except yum.Errors.InstallError,e:
                msgs = '\n'.join(e)
                self._unlock_yum()
                self.ErrorCode(ERROR_PACKAGE_ALREADY_INSTALLED,msgs)
                self.Finished(EXIT_FAILED)
                return
        else:
            self._unlock_yum()
            self.ErrorCode(ERROR_PACKAGE_NOT_FOUND,"Package was not found")
            self.Finished(EXIT_FAILED)
            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doInstallFile (self, inst_file):
        '''
        Implement the {backend}-install_file functionality
        Install the package containing the inst_file file
        Needed to be implemented in a sub class
        '''
        if inst_file.endswith('.src.rpm'):
            self.ErrorCode(ERROR_CANNOT_INSTALL_SOURCE_PACKAGE,'Backend will not install a src rpm file')
            self.Finished(EXIT_FAILED)
            return
        
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.PercentageChanged(0)
        self.StatusChanged(STATUS_QUERY)

        pkgs_to_inst = []
        self.yumbase.conf.gpgcheck=0
        txmbr = self.yumbase.installLocal(inst_file)
        self._checkForNewer(txmbr[0].po)
        po = txmbr[0].po
        self.AllowCancel(False)
        self.StatusChanged(STATUS_INSTALL)

        try:
            if po.arch == 'src':
                # Special case for source package - don't resolve deps
                rpmDisplay = PackageKitCallback(self)
                callback = ProcessTransPackageKitCallback(self)
                self.yumbase._doTransaction(callback,
                                            display=rpmDisplay)
            else:
                # Added the package to the transaction set
                if len(self.yumbase.tsInfo) > 0:
                    successful = self._runYumTransaction()
                    if not successful:
                        return
                    else:
                        self.StatusChanged(STATUS_CLEANUP)
        except yum.Errors.InstallError,e:
            msgs = '\n'.join(e)
            self._unlock_yum()
            self.ErrorCode(ERROR_PACKAGE_ALREADY_INSTALLED,msgs)
            self.Finished(EXIT_FAILED)
            return
        except yum.Errors.YumBaseError, ye:
            retmsg = "Could not install package:\n" + ye.value
            self._unlock_yum()
            self.ErrorCode(ERROR_TRANSACTION_ERROR,retmsg)
            self.Finished(EXIT_FAILED)
            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doUpdatePackages(self, packages):
        '''
        Implement the {backend}-update functionality
        This will only work with yum 3.2.4 or higher
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(False)
        self.PercentageChanged(0)
        self.StatusChanged(STATUS_RUNNING)

        for package_id in packages:
            package, installed = self._findPackage(package_id)

            if not package:
                self._unlock_yum()
                self.ErrorCode(ERROR_PACKAGE_NOT_FOUND, "%s could not be found." % package_id)
                self.Finished(EXIT_FAILED)
                return

            if installed:
                self._unlock_yum()
                self.ErrorCode(ERROR_PACKAGE_ALREADY_INSTALLED, "%s is already installed." % package_id)
                self.Finished(EXIT_FAILED)
                return

            txmbr = self.yumbase.update(po=package)

            if not txmbr:
                self._unlock_yum()
                self.ErrorCode(ERROR_TRANSACTION_ERROR,
                               "Package %s could not be added to the transaction." % package_id)
                self.Finished(EXIT_FAILED)
                return

        successful = self._runYumTransaction()

        if not successful:
            # _runYumTransaction() sets the error code and calls Finished()
            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doRemovePackage(self, package, allowdep, autoremove):
        '''
        Implement the {backend}-remove functionality
        '''
        self.last_action_time = time.time()
        self._check_init()
        self._lock_yum()
        self.AllowCancel(False)
        self.PercentageChanged(0)
        self.StatusChanged(STATUS_RUNNING)

        pkg,inst = self._findPackage( package)
        if pkg and inst:
            txmbr = self.yumbase.remove(name=pkg.name)
            if txmbr:
                if allowdep:
                    successful = self._runYumTransaction(removedeps=True)
                    if not successful:
                        return
                else:
                    successful = self._runYumTransaction(removedeps=False)
                    if not successful:
                        return
            else:
                self._unlock_yum()
                self.ErrorCode(ERROR_PACKAGE_NOT_INSTALLED,"Package is not installed")
                self.Finished(EXIT_FAILED)
                return

            self._unlock_yum()
            self.Finished(EXIT_SUCCESS)
        else:
            self._unlock_yum()
            self.ErrorCode(ERROR_PACKAGE_NOT_INSTALLED,"Package is not installed")
            self.Finished(EXIT_FAILED)
        return

    @threaded
    @async
    def doGetDescription(self, package):
        '''
        Print a detailed description for a given package
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_INFO)

        pkg,inst = self._findPackage(package)

        if self._cancel_check("Action cancelled."):
            # _cancel_check() sets the error message, unlocks yum, and calls Finished()
            return

        if pkg:
            self._show_package_description(pkg)
        else:
            self._unlock_yum()
            self.ErrorCode(ERROR_PACKAGE_NOT_FOUND,'Package was not found')
            self.Finished(EXIT_FAILED)
            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doGetFiles(self, package):
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_INFO)

        pkg,inst = self._findPackage(package)

        if self._cancel_check("Action cancelled."):
            # _cancel_check() sets the error message, unlocks yum, and calls Finished()
            return

        if pkg:
            files = pkg.returnFileEntries('dir')
            files.extend(pkg.returnFileEntries()) # regular files

            file_list = ";".join(files)

            self.Files(package, file_list)
        else:
            self._unlock_yum()
            self.ErrorCode(ERROR_PACKAGE_NOT_FOUND,'Package was not found')
            self.Finished(EXIT_FAILED)
            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doGetUpdates(self, filters):
        '''
        Implement the {backend}-get-updates functionality
        @param filters: package types to show
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_INFO)

        fltlist = filters.split(';')

        try:
            ygl = self.yumbase.doPackageLists(pkgnarrow='updates')
            md = self.updateMetadata
            for pkg in ygl.updates:
                if self._cancel_check("Action cancelled."):
                    # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                    return

                if self._do_extra_filtering(pkg, fltlist):
                    # Get info about package in updates info
                    notice = md.get_notice((pkg.name, pkg.version, pkg.release))
                    if notice:
                        status = self._get_status(notice)
                        self._show_package(pkg,status)
                    else:
                        self._show_package(pkg,INFO_NORMAL)
        except yum.Errors.RepoError,e:
            self.Message(MESSAGE_NOTICE, "The package cache is invalid and is being rebuilt.")
            self._refresh_yum_cache()
            self._unlock_yum()
            self.Finished(EXIT_FAILED)

            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doGetPackages(self,filters,showdesc='no'):
        '''
        Search for yum packages
        @param searchlist: The yum package fields to search in
        @param filters: package types to search (all,installed,available)
        @param key: key to seach for
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_QUERY)

        showDesc = (showdesc == 'yes' or showdesc == 'only' )
        showPkg = (showdesc != 'only')
        try:
            fltlist = filters.split(';')
            available = []
            count = 1
            if FILTER_NOT_INSTALLED not in fltlist:
                for pkg in self.yumbase.rpmdb:
                    if self._cancel_check("Action cancelled."):
                        # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                        return

                    if self._do_extra_filtering(pkg,fltlist):
                        if showPkg:
                            self._show_package(pkg, INFO_INSTALLED)
                        if showDesc:
                            self._show_package_description(pkg)


        # Now show available packages.
            if FILTER_INSTALLED not in fltlist:
                for pkg in self.yumbase.pkgSack.returnNewestByNameArch():
                    if self._cancel_check("Action cancelled."):
                        # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                        return

                    if self._do_extra_filtering(pkg,fltlist):
                        if showPkg:
                            self._show_package(pkg, INFO_AVAILABLE)
                        if showDesc:
                            self._show_package_description(pkg)
        except yum.Errors.RepoError,e:
            self.Message(MESSAGE_NOTICE, "The package cache is invalid and is being rebuilt.")
            self._refresh_yum_cache()
            self._unlock_yum()
            self.Finished(EXIT_FAILED)

            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doRepoEnable(self, repoid, enable):
        '''
        Implement the {backend}-repo-enable functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(False)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_SETUP)

        try:
            repo = self.yumbase.repos.getRepo(repoid)
            if enable:
                if not repo.isEnabled():
                    repo.enablePersistent()
                    repo.metadata_expire = 60 * 60 * 1.5 # 1.5 hours, the default
                    repo.mdpolicy = "group:all"
            else:
                if repo.isEnabled():
                    repo.disablePersistent()

        except yum.Errors.RepoError,e:
            self._unlock_yum()
            self.ErrorCode(ERROR_REPO_NOT_FOUND, "repo %s is not found" % repoid)
            self.Finished(EXIT_FAILED)
            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doGetRepoList(self, filters):
        '''
        Implement the {backend}-get-repo-list functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(False)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_INFO)

        for repo in self.yumbase.repos.repos.values():
            if repo.isEnabled():
                self.RepoDetail(repo.id,repo.name,True)
            else:
                self.RepoDetail(repo.id,repo.name,False)

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doGetUpdateDetail(self,package):
        '''
        Implement the {backend}-get-update_detail functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_INFO)

        pkg,inst = self._findPackage(package)

        if not pkg:
            self._unlock_yum()
            self.ErrorCode(ERROR_PACKAGE_NOT_FOUND,'Package was not found')
            self.Finished(EXIT_FAILED)
            return

        if self._cancel_check("Action cancelled."):
            # _cancel_check() sets the error message, unlocks yum, and calls Finished()
            return

        update = self._get_updated(pkg)
        obsolete = self._get_obsoleted(pkg.name)
        desc,urls,reboot = self._get_update_extras(pkg)
        cve_url = self._format_list(urls['cve'])
        bz_url = self._format_list(urls['bugzilla'])
        vendor_url = self._format_list(urls['vendor'])

        self._show_update_detail(pkg,update,obsolete,vendor_url,bz_url,cve_url,reboot,desc)

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doRepoSetData(self, repoid, parameter, value):
        '''
        Implement the {backend}-repo-set-data functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(False)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_SETUP)

        # Get the repo
        repo = self.yumbase.repos.getRepo(repoid)
        if repo:
            repo.cfg.set(repoid, parameter, value)
            try:
                repo.cfg.write(file(repo.repofile, 'w'))
            except IOError, e:
                self._unlock_yum()
                self.ErrorCode(ERROR_CANNOT_WRITE_REPO_CONFIG,str(e))
                self.Finished(EXIT_FAILED)
                return
        else:
            self._unlock_yum()
            self.ErrorCode(ERROR_REPO_NOT_FOUND,'repo %s not found' % repoid)
            self.Finished(EXIT_FAILED)
            return

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doInstallPublicKey(self, keyurl):
        '''
        Implement the {backend}-install-public-key functionality
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.PercentageChanged(0)
        self.StatusChanged(STATUS_RUNNING)

        # Go get the GPG key from the given URL
        try:
            rawkey = urlgrabber.urlread(keyurl, limit=9999)
        except urlgrabber.grabber.URLGrabError, e:
            self.ErrorCode(ERROR_GPG_FAILURE, 'GPG key retrieval failed: ' +
                           str(e))
            self._unlock_yum()
            self.Finished(EXIT_FAILED)
            return

        if self._cancel_check("Action cancelled."):
            # _cancel_check() sets the error message, unlocks yum, and calls Finished()
            return

        self.PercentageChanged(50)

        keyinfo = {}
        # Parse the key
        try:
            keyinfo = getgpgkeyinfo(rawkey)
        except ValueError, e:
            raise Errors.YumBaseError, \
                      'GPG key parsing failed: ' + str(e)

        if self._cancel_check("Action cancelled."):
            # _cancel_check() sets the error message, unlocks yum, and calls Finished()
            return

        keyinfo['keyurl'] = keyurl
        keyinfo['hexkeyid'] = keyIdToRPMVer(keyinfo['keyid']).upper()

        ts = rpmUtils.transaction.TransactionWrapper(self.yumbase.conf.installroot)

        if self._cancel_check("Action cancelled."):
            # _cancel_check() sets the error message, unlocks yum, and calls Finished()
            return

        # Check if key is already installed
        if keyInstalled(ts, keyinfo['keyid'], keyinfo['timestamp']) >= 0:
            self.ErrorCode(ERROR_GPG_FAILURE, "GPG key at %s (0x%s) is already installed" %
                           (keyinfo['keyurl'], keyinfo['hexkeyid']))
            self._unlock_yum()
            self.Finished(EXIT_FAILED)
            return

        if self._cancel_check("Action cancelled."):
            # _cancel_check() sets the error message, unlocks yum, and calls Finished()
            return

        self.AllowCancel(False)

        self.PercentageChanged(75)

        # Import the key
        result = ts.pgpImportPubkey(procgpgkey(rawkey))
        if result != 0:
            self.ErrorCode(ERROR_GPG_FAILURE, 'GPG key import failed (code %d)' % result)
            self._unlock_yum()
            self.Finished(EXIT_FAILED)
            return

        self.PercentageChanged(100)

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

    @threaded
    @async
    def doWhatProvides(self, filters, provides_type, search):
        '''
        Provide a list of packages that satisfy a given requirement.

        The yum backend ignores the provides_type - the search string
        should always be a standard rpm provides.
        '''
        self._check_init()
        self._lock_yum()
        self.AllowCancel(True)
        self.NoPercentageUpdates()
        self.StatusChanged(STATUS_INFO)
        
        fltlist = filters.split(';')

        if not FILTER_NOT_INSTALLED in fltlist:
            results = self.yumbase.pkgSack.searchProvides(search)
            for result in results:
                if self._cancel_check("Action cancelled."):
                    # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                    return

                if self._do_extra_filtering(result, fltlist):
                    self._show_package(result,INFO_AVAILABLE)
                
        if not FILTER_INSTALLED in fltlist:
            results = self.yumbase.rpmdb.searchProvides(search)
            for result in results:
                if self._cancel_check("Action cancelled."):
                    # _cancel_check() sets the error message, unlocks yum, and calls Finished()
                    return

                if self._do_extra_filtering(result, fltlist):
                    self._show_package(result,INFO_INSTALLED)

        self._unlock_yum()
        self.Finished(EXIT_SUCCESS)

#
# Utility methods for Methods
#

    def _do_search(self,searchlist,filters,key):
        '''
        Search for yum packages
        @param searchlist: The yum package fields to search in
        @param filters: package types to search (all,installed,available)
        @param key: key to seach for
        '''
        try:
            res = self.yumbase.searchGenerator(searchlist, [key])
            fltlist = filters.split(';')

            available = []
            count = 1
            for (pkg,values) in res:
                if self._cancel_check("Search cancelled."):
                    return False
                # are we installed?
                if pkg.repo.id == 'installed':
                    if FILTER_NOT_INSTALLED not in fltlist:
                        if self._do_extra_filtering(pkg,fltlist):
                            count+=1
                            if count > 100:
                                break
                            self._show_package(pkg, INFO_INSTALLED)
                else:
                    available.append(pkg)

            # Now show available packages.
            if FILTER_INSTALLED not in fltlist:
                for pkg in available:
                    if self._cancel_check("Search cancelled."):
                        return False
                    if self._do_extra_filtering(pkg,fltlist):
                        self._show_package(pkg, INFO_AVAILABLE)

        except yum.Errors.RepoError,e:
            self.Message(MESSAGE_NOTICE, "The package cache is invalid and is being rebuilt.")
            self._refresh_yum_cache()
            self._unlock_yum()
            self.Finished(EXIT_FAILED)

            return False

        return True

    def _do_extra_filtering(self,pkg,filterList):
        ''' do extra filtering (gui,devel etc) '''
        for filter in filterList:
            if filter in (FILTER_INSTALLED, FILTER_NOT_INSTALLED):
                continue
            elif filter in (FILTER_GUI, FILTER_NOT_GUI):
                if not self._do_gui_filtering(filter, pkg):
                    return False
            elif filter in (FILTER_DEVELOPMENT, FILTER_NOT_DEVELOPMENT):
                if not self._do_devel_filtering(filter, pkg):
                    return False
            elif filter in (FILTER_FREE, FILTER_NOT_FREE):
                if not self._do_free_filtering(filter, pkg):
                    return False
            elif filter in (FILTER_BASENAME, FILTER_NOT_BASENAME):
                if not self._do_basename_filtering(filter, pkg):
                    return False
        return True

    def _do_gui_filtering(self,flt,pkg):
        isGUI = False
        if flt == FILTER_GUI:
            wantGUI = True
        else:
            wantGUI = False
        isGUI = self._check_for_gui(pkg)
        return isGUI == wantGUI

    def _check_for_gui(self,pkg):
        '''  Check if the GUI_KEYS regex matches any package requirements'''
        for req in pkg.requires:
            reqname = req[0]
            if GUI_KEYS.search(reqname):
                return True
        return False

    def _do_devel_filtering(self,flt,pkg):
        isDevel = False
        if flt == FILTER_DEVELOPMENT:
            wantDevel = True
        else:
            wantDevel = False
        regex =  re.compile(r'(-devel)|(-dgb)|(-static)')
        if regex.search(pkg.name):
            isDevel = True
        return isDevel == wantDevel

    def _do_free_filtering(self,flt,pkg):
        isFree = False
        if flt == FILTER_FREE:
            wantFree = True
        else:
            wantFree = False

        isFree = self.check_license_field(pkg.license)

        return isFree == wantFree

    def _do_basename_filtering(self,flt,pkg):
        if flt == FILTER_BASENAME:
            wantBase = True
        else:
            wantBase = False

        isBase = self._check_basename(pkg)

        return isBase == wantBase

    def _check_basename(self, pkg):
        '''
        If a package does not have a source rpm (If that ever
        happens), or it does have a source RPM, and the package's name
        is the same as the source RPM's name, then we assume it is the
        'base' package.
        '''
        basename = pkg.name

        if pkg.sourcerpm:
            basename = rpmUtils.miscutils.splitFilename(pkg.sourcerpm)[0]

        if basename == pkg.name:
            return True

        return False

    def _buildGroupDict(self):
        pkgGroups= {}
        cats = self.yumbase.comps.categories
        for cat in cats:
            grps = map( lambda x: self.yumbase.comps.return_group( x ),
               filter( lambda x: self.yumbase.comps.has_group( x ), cat.groups ) )
            grplist = []
            for group in grps:
                for pkg in group.mandatory_packages.keys():
                    pkgGroups[pkg] = "%s;%s" % (cat.categoryid,group.groupid)
                for pkg in group.default_packages.keys():
                    pkgGroups[pkg] = "%s;%s" % (cat.categoryid,group.groupid)
                for pkg in group.optional_packages.keys():
                    pkgGroups[pkg] = "%s;%s" % (cat.categoryid,group.groupid)
                for pkg in group.conditional_packages.keys():
                    pkgGroups[pkg] = "%s;%s" % (cat.categoryid,group.groupid)
        return pkgGroups

    def _show_package_description(self,pkg):
        pkgver = self._get_package_ver(pkg)
        id = self._get_package_id(pkg.name, pkgver, pkg.arch, pkg.repo)
        desc = pkg.description
        desc = desc.replace('\n\n','__PARAGRAPH_SEPARATOR__')
        desc = desc.replace('\n',' ')
        desc = desc.replace('__PARAGRAPH_SEPARATOR__','\n')

        self._show_description(id, pkg.license, "unknown", desc, pkg.url,
                             pkg.size)

    def _getEVR(self,idver):
        '''
        get the e,v,r from the package id version
        '''
        cpos = idver.find(':')
        if cpos != -1:
            epoch = idver[:cpos]
            idver = idver[cpos+1:]
        else:
            epoch = '0'
        (version,release) = tuple(idver.split('-'))
        return epoch,version,release

    def _checkForNewer(self,po):
        '''
        Check if there is a newer version available
        '''
        pkgs = self.yumbase.pkgSack.returnNewestByName(name=po.name)
        if pkgs:
            newest = pkgs[0]
            if newest.EVR > po.EVR:
                #TODO Add code to send a message here
                self.Message(MESSAGE_WARNING,"Newer version of %s, exist in the repositories " % po.name)



    def _findPackage(self,id):
        '''
        find a package based on a package id (name;version;arch;repoid)
        '''
        # Split up the id
        (n,idver,a,d) = self.get_package_from_id(id)
        # get e,v,r from package id version
        e,v,r = self._getEVR(idver)
        # search the rpmdb for the nevra
        pkgs = self.yumbase.rpmdb.searchNevra(name=n,epoch=e,ver=v,rel=r,arch=a)
        # if the package is found, then return it
        if len(pkgs) != 0:
            return pkgs[0],True
        # search the pkgSack for the nevra
        pkgs = self.yumbase.pkgSack.searchNevra(name=n,epoch=e,ver=v,rel=r,arch=a)
        # if the package is found, then return it
        if len(pkgs) != 0:
            return pkgs[0],False
        else:
            return None,False

    def _is_inst(self,pkg):
        return self.yumbase.rpmdb.installed(po=pkg)
        
        

    def _installable(self, pkg, ematch=False):

        """check if the package is reasonably installable, true/false"""

        exactarchlist = self.yumbase.conf.exactarchlist
        # we look through each returned possibility and rule out the
        # ones that we obviously can't use

        if self._is_inst(pkg):
            return False

        # everything installed that matches the name
        installedByKey = self.yumbase.rpmdb.searchNevra(name=pkg.name)
        comparable = []
        for instpo in installedByKey:
            if rpmUtils.arch.isMultiLibArch(instpo.arch) == rpmUtils.arch.isMultiLibArch(pkg.arch):
                comparable.append(instpo)
            else:
                continue

        # go through each package
        if len(comparable) > 0:
            for instpo in comparable:
                if pkg.EVR > instpo.EVR: # we're newer - this is an update, pass to them
                    if instpo.name in exactarchlist:
                        if pkg.arch == instpo.arch:
                            return True
                    else:
                        return True

                elif pkg.EVR == instpo.EVR: # same, ignore
                    return False

                elif pkg.EVR < instpo.EVR: # lesser, check if the pkgtup is an exactmatch
                                   # if so then add it to be installed
                                   # if it can be multiply installed
                                   # this is where we could handle setting
                                   # it to be an 'oldpackage' revert.

                    if ematch and self.yumbase.allowedMultipleInstalls(pkg):
                        return True

        else: # we've not got any installed that match n or n+a
            return True

        return False

    def _get_best_dependencies(self,po):
        ''' find the most recent packages that provides the dependencies for a package
        @param po: yum package object to find deps for
        @return: a list for yum package object providing the dependencies
        '''
        results = self.yumbase.findDeps([po])
        pkg = results.keys()[0]
        bestdeps=[]
        dep_resolution_errors=[]
        if len(results[pkg].keys()) == 0: # No dependencies for this package ?
            return bestdeps
        for req in results[pkg].keys():
            reqlist = results[pkg][req]
            if not reqlist: #  Unsatisfied dependency
                dep_resolution_errors.append(prco_tuple_to_string(req))
                continue
            best = None
            for po in reqlist:
                if best:
                    if po.EVR > best.EVR:
                        best=po
                else:
                    best= po
            bestdeps.append(best)

        return (dep_resolution_errors, unique(bestdeps))

    def _check_for_reboot(self):
        md = self.updateMetadata
        for txmbr in self.yumbase.tsInfo:
            pkg = txmbr.po
            # check if package is in reboot list or flagged with reboot_suggested
            # in the update metadata and is installed/updated etc
            notice = md.get_notice((pkg.name, pkg.version, pkg.release))
            if (pkg.name in self.rebootpkgs \
                or (notice and notice.get_metadata().has_key('reboot_suggested') and notice['reboot_suggested']))\
                and txmbr.ts_state in TS_INSTALL_STATES:
                self.require_restart(RESTART_SYSTEM,"")
                break

    def _runYumTransaction(self,removedeps=None):
        '''
        Run the yum Transaction
        This will only work with yum 3.2.4 or higher
        Returns True on success, False on failure
        '''

        rc,msgs =  self.yumbase.buildTransaction()
        if rc !=2:
            retmsg = "Error in Dependency Resolution\n" +"\n".join(msgs)
            self._unlock_yum()
            self.ErrorCode(ERROR_DEP_RESOLUTION_FAILED,retmsg)
            self.Finished(EXIT_FAILED)
            return False

        self._check_for_reboot()

        if removedeps == False and len(self.yumbase.tsInfo) > 1:
            retmsg = 'package could not be removed, as other packages depend on it'
            self._unlock_yum()
            self.ErrorCode(ERROR_DEP_RESOLUTION_FAILED,retmsg)
            self.Finished(EXIT_FAILED)
            return False

        try:
            rpmDisplay = PackageKitCallback(self)
            callback = ProcessTransPackageKitCallback(self)
            self.yumbase.processTransaction(callback=callback,
                                            rpmDisplay=rpmDisplay)
        except yum.Errors.YumDownloadError, ye:
            retmsg = "Error in Download\n" + "\n".join(ye.value)
            self._unlock_yum()
            self.ErrorCode(ERROR_PACKAGE_DOWNLOAD_FAILED,retmsg)
            self.Finished(EXIT_FAILED)
            return False
        except yum.Errors.YumGPGCheckError, ye:
            retmsg = "Error in Package Signatures\n" +"\n".join(ye.value)
            self._unlock_yum()
            self.ErrorCode(ERROR_BAD_GPG_SIGNATURE,retmsg)
            self.Finished(EXIT_FAILED)
            return False
        except GPGKeyNotImported, e:
            keyData = self.yumbase.missingGPGKey
            if not keyData:
                self._unlock_yum()
                self.ErrorCode(ERROR_BAD_GPG_SIGNATURE,
                               "GPG key not imported, but no GPG information received from Yum.")
                self.Finished(EXIT_FAILED)
                return False
            self.RepoSignatureRequired(keyData['po'].repoid,
                                       keyData['keyurl'],
                                       keyData['userid'],
                                       keyData['hexkeyid'],
                                       keyData['fingerprint'],
                                       keyData['timestamp'],
                                       SIGTYE_GPG)
            self._unlock_yum()
            self.ErrorCode(ERROR_GPG_FAILURE,"GPG key not imported.")
            self.Finished(EXIT_FAILED)
            return False
        except yum.Errors.YumBaseError, ye:
            retmsg = "Error in Transaction Processing\n" + "\n".join(ye.value)
            self._unlock_yum()
            self.ErrorCode(ERROR_TRANSACTION_ERROR,retmsg)
            self.Finished(EXIT_FAILED)
            return False

        return True

    def _get_status(self,notice):
        ut = notice['type']
        if ut == 'security':
            return INFO_SECURITY
        elif ut == 'bugfix':
            return INFO_BUGFIX
        elif ut == 'enhancement':
            return INFO_ENHANCEMENT
        else:
            return INFO_UNKNOWN

    def _get_obsoleted(self,name):
        obsoletes = self.yumbase.up.getObsoletesTuples( newest=1 )
        for ( obsoleting, installed ) in obsoletes:
            if obsoleting[0] == name:
                pkg =  self.yumbase.rpmdb.searchPkgTuple( installed )[0]
                return self._pkg_to_id(pkg)
        return ""

    def _get_updated(self,pkg):
        updated = None
        pkgs = self.yumbase.rpmdb.searchNevra(name=pkg.name)
        if pkgs:
            return self._pkg_to_id(pkgs[0])
        else:
            return ""

    def _get_update_metadata(self):
        if not self._updateMetadata:
            self._updateMetadata = UpdateMetadata()
            for repo in self.yumbase.repos.listEnabled():
                try:
                    self._updateMetadata.add(repo)
                except:
                    pass # No updateinfo.xml.gz in repo
        return self._updateMetadata

    _updateMetadata = None
    updateMetadata = property(fget=_get_update_metadata)

    def _format_list(self,lst):
        """
        Convert a list to a multiline string
        """
        if lst:
            return "\n".join(lst)
        else:
            return ""

    def _get_update_extras(self,pkg):
        urls = {'bugzilla': [], 'cve': [], 'vendor': []}
        notice = self.updateMetadata.get_notice((pkg.name, pkg.version, pkg.release))
        if notice:
            # Update Description
            desc = notice['description']

            # Update References (Bugzilla,CVE ...)
            for ref in notice['references']:
                type_ = ref['type']
                href = ref['href']
                title = ref['title'] or ""

                # Description can sometimes have ';' in them, and we use that as the delimiter
                title = title.replace(";",",")

                if href:
                    if type_ in ('bugzilla', 'cve'):
                        urls[type_].append("%s;%s" % (href, title))
                    else:
                        urls['vendor'].append("%s;%s" % (href, title))

            # Reboot flag
            if notice.get_metadata().has_key('reboot_suggested') and notice['reboot_suggested']:
                reboot = 'system'
            else:
                reboot = 'none'
            return desc,urls,reboot
        else:
            return "",urls,"none"

#
# Other utility methods
#

    def _customTracebackHandler(self,exctype):
        '''
        Handle special not catched Tracebacks
        '''
        # Handle misc errors with loading repository metadata
        if (issubclass(exctype, yum.Errors.RepoError) or
            issubclass(exctype, IOError)):
            self.ErrorCode(ERROR_NO_NETWORK, "Problem with loading repository metadata, this can be caused by network problems or repository misconfigurations")
            self.Finished(EXIT_FAILED)
            return True
        else:
            return False

    def _check_init(self):
        ''' Check if yum has setup, else call init '''
        if hasattr(self,'yumbase'):
            self.dnlCallback.reset()
        else:
            self.doInit()

    def _get_package_ver(self,po):
        ''' return the a ver as epoch:version-release or version-release, if epoch=0'''
        if po.epoch != '0':
            ver = "%s:%s-%s" % (po.epoch,po.version,po.release)
        else:
            ver = "%s-%s" % (po.version,po.release)
        return ver

    def _refresh_yum_cache(self):
        self.StatusChanged(STATUS_REFRESH_CACHE)
        old_cache_setting = self.yumbase.conf.cache
        self.yumbase.conf.cache = 0
        self.yumbase.repos.setCache(0)

        self.yumbase.repos.populateSack(mdtype='metadata', cacheonly=1)
        self.yumbase.repos.populateSack(mdtype='filelists', cacheonly=1)
        self.yumbase.repos.populateSack(mdtype='otherdata', cacheonly=1)

        self.yumbase.conf.cache = old_cache_setting
        self.yumbase.repos.setCache(old_cache_setting)

    def _setup_yum(self):
        self.yumbase.doConfigSetup(errorlevel=0,debuglevel=0)     # Setup Yum Config

        # Setup caching strategy for all repos.
        for repo in self.yumbase.repos.listEnabled():
            repo.metadata_expire = 60 * 60 * 1.5  # 1.5 hours, the default
            repo.mdpolicy = "group:all"

        self.yumbase.conf.throttle = "90%"                        # Set bandwidth throttle to 90%
        self.dnlCallback = DownloadCallback(self,showNames=True)  # Download callback
        self.yumbase.repos.setProgressBar( self.dnlCallback )     # Setup the download callback class

class DownloadCallback( BaseMeter ):
    """ Customized version of urlgrabber.progress.BaseMeter class """
    def __init__(self,base,showNames = False):
        BaseMeter.__init__( self )
        self.totSize = ""
        self.base = base
        self.showNames = showNames
        self.reset()

    def reset(self):
        '''Reset download callback for a new transaction.'''
        self.oldName = None
        self.lastPct = 0
        self.totalPct = 0
        self.pkgs = None
        self.numPkgs = 0
        self.bump = 0.0

    def setPackages(self,pkgs,startPct,numPct):
        self.pkgs = pkgs
        self.numPkgs = float(len(self.pkgs))
        self.bump = numPct/self.numPkgs
        self.totalPct = startPct

    def _getPackage(self,name):
        if self.pkgs:
            for pkg in self.pkgs:
                rpmfn = os.path.basename(pkg.remote_path) # get the rpm filename of the package
                if rpmfn == name:
                    return pkg
        return None

    def update( self, amount_read, now=None ):
        BaseMeter.update( self, amount_read, now )

    def _do_start( self, now=None ):
        name = self._getName()
        self.updateProgress(name,0.0,"","")
        if not self.size is None:
            self.totSize = format_number( self.size )

    def _do_update( self, amount_read, now=None ):
        fread = format_number( amount_read )
        name = self._getName()
        if self.size is None:
            # Elapsed time
            etime = self.re.elapsed_time()
            fetime = format_time( etime )
            frac = 0.0
            self.updateProgress(name,frac,fread,fetime)
        else:
            # Remaining time
            rtime = self.re.remaining_time()
            frtime = format_time( rtime )
            frac = self.re.fraction_read()
            self.updateProgress(name,frac,fread,frtime)

    def _do_end( self, amount_read, now=None ):
        total_time = format_time( self.re.elapsed_time() )
        total_size = format_number( amount_read )
        name = self._getName()
        self.updateProgress(name,1.0,total_size,total_time)

    def _getName(self):
        '''
        Get the name of the package being downloaded
        '''
        if self.text and type( self.text ) == type( "" ):
            name = self.text
        else:
            name = self.basename
        return name

    def updateProgress(self,name,frac,fread,ftime):
        '''
         Update the progressbar (Overload in child class)
        @param name: filename
        @param frac: Progress fracment (0 -> 1)
        @param fread: formated string containing BytesRead
        @param ftime : formated string containing remaining or elapsed time
        '''
        pct = int( frac*100 )
        if name != self.oldName: # If this a new package
            if self.oldName:
                self.base.SubPercentageChanged(100)
            self.oldName = name
            if self.bump > 0.0: # Bump the total download percentage
                self.totalPct += self.bump
                self.lastPct = 0
                self.base.PercentageChanged(int(self.totalPct))
            if self.showNames:
                pkg = self._getPackage(name)
                if pkg: # show package to download
                    self.base._show_package(pkg,INFO_DOWNLOADING)
                else:
                    typ = STATUS_DOWNLOAD_REPOSITORY
                    for key in MetaDataMap.keys():
                        if key in name:
                            typ = MetaDataMap[key]
                            break
                    self.base.StatusChanged(typ)
            self.base.SubPercentageChanged(0)
        else:
            if self.lastPct != pct and pct != 0 and pct != 100:
                self.lastPct = pct
            # bump the sub percentage for this package
                self.base.SubPercentageChanged(pct)

class PackageKitCallback(RPMBaseCallback):
    def __init__(self,base):
        RPMBaseCallback.__init__(self)
        self.base = base
        self.pct = 0
        self.curpkg = None
        self.startPct = 50
        self.numPct = 50
        # Map yum transactions with pk info enums
        self.info_actions = { TS_UPDATE : INFO_UPDATING,
                        TS_ERASE: INFO_REMOVING,
                        TS_INSTALL: INFO_INSTALLING,
                        TS_TRUEINSTALL : INFO_INSTALLING,
                        TS_OBSOLETED: INFO_OBSOLETING,
                        TS_OBSOLETING: INFO_INSTALLING,
                        TS_UPDATED: INFO_CLEANUP}

        # Map yum transactions with pk state enums
        self.state_actions = { TS_UPDATE : STATUS_UPDATE,
                        TS_ERASE: STATUS_REMOVE,
                        TS_INSTALL: STATUS_INSTALL,
                        TS_TRUEINSTALL : STATUS_INSTALL,
                        TS_OBSOLETED: STATUS_OBSOLETE,
                        TS_OBSOLETING: STATUS_INSTALL,
                        TS_UPDATED: STATUS_CLEANUP}

    def _calcTotalPct(self,ts_current,ts_total):
        bump = float(self.numPct)/ts_total
        pct = int(self.startPct + (ts_current * bump))
        return pct

    def _showName(self,status):
        if type(self.curpkg) in types.StringTypes:
            id = self.base._get_package_id(self.curpkg,'','','')
        else:
            pkgver = self.base._get_package_ver(self.curpkg)
            id = self.base._get_package_id(self.curpkg.name, pkgver, self.curpkg.arch, self.curpkg.repo)
        self.base.Package(status, id, "")

    def event(self, package, action, te_current, te_total, ts_current, ts_total):
        if self.base._cancel_check("Action cancelled."):
            sys.exit(0)

        if str(package) != str(self.curpkg):
            self.curpkg = package
            self.base.StatusChanged(self.state_actions[action])
            self._showName(self.info_actions[action])
            pct = self._calcTotalPct(ts_current, ts_total)
            self.base.PercentageChanged(pct)
        val = (ts_current*100L)/ts_total
        if val != self.pct:
            self.pct = val
            self.base.SubPercentageChanged(val)

    def errorlog(self, msg):
        # grrrrrrrr
        pass

class ProcessTransPackageKitCallback:
    def __init__(self,base):
        self.base = base

    def event(self,state,data=None):
        if state == PT_DOWNLOAD:        # Start Downloading
            self.base.AllowCancel(True)
            self.base.PercentageChanged(10)
            self.base.StatusChanged(STATUS_DOWNLOAD)
        if state == PT_DOWNLOAD_PKGS:   # Packages to download
            self.base.dnlCallback.setPackages(data,10,30)
        elif state == PT_GPGCHECK:
            self.base.PercentageChanged(40)
            self.base.StatusChanged(STATUS_SIG_CHECK)
            pass
        elif state == PT_TEST_TRANS:
            self.base.AllowCancel(False)
            self.base.PercentageChanged(45)
            self.base.StatusChanged(STATUS_TEST_COMMIT)
            pass
        elif state == PT_TRANSACTION:
            self.base.AllowCancel(False)
            self.base.PercentageChanged(50)
            pass


class DepSolveCallback(object):

    # XXX takes a PackageKitBackend so we can call StatusChanged on it.
    # That's kind of hurky.
    def __init__(self, backend):
        self.started = False
        self.backend = backend

    def start(self):
       if not self.started:
           self.backend.StatusChanged(STATUS_DEP_RESOLVE)
           self.backend.NoPercentageUpdates()

    # Be lazy and not define the others explicitly
    def _do_nothing(self, *args, **kwargs):
        pass

    def __getattr__(self, x):
        return self._do_nothing


class PackageKitYumBase(yum.YumBase):
    """
    Subclass of YumBase.  Needed so we can overload _checkSignatures
    and nab the gpg sig data
    """

    def __init__(self, backend):
        yum.YumBase.__init__(self)
        self.missingGPGKey = None
        self.skipped_packages = []
        self.dsCallback = DepSolveCallback(backend)

    # Modified searchGenerator to make sure that
    # non unicode strings read from rpmdb is converted to unicode
    # FIXME: Remove this when fixed and released in upstream
    def searchGenerator(self, fields, criteria, showdups=True):
        """Generator method to lighten memory load for some searches.
           This is the preferred search function to use."""
        sql_fields = []
        for f in fields:
            if RPM_TO_SQLITE.has_key(f):
                sql_fields.append(RPM_TO_SQLITE[f])
            else:
                sql_fields.append(f)

        matched_values = {}

        # yield the results in order of most terms matched first
        sorted_lists = {}
        tmpres = []
        real_crit = []
        for s in criteria:
            if s.find('%') == -1:
                real_crit.append(s)
        real_crit_lower = [] # Take the s.lower()'s out of the loop
        for s in criteria:
            if s.find('%') == -1:
                real_crit_lower.append(s.lower())

        for sack in self.pkgSack.sacks.values():
            tmpres.extend(sack.searchPrimaryFieldsMultipleStrings(sql_fields, real_crit))

        for (po, count) in tmpres:
            # check the pkg for sanity
            # pop it into the sorted lists
            tmpvalues = []
            if count not in sorted_lists: sorted_lists[count] = []
            for s in real_crit_lower:
                for field in fields:
                    value = getattr(po, field)
                    if value and value.lower().find(s) != -1:
                        tmpvalues.append(value)

            if len(tmpvalues) > 0:
                sorted_lists[count].append((po, tmpvalues))



        for po in self.rpmdb:
            tmpvalues = []
            criteria_matched = 0
            for s in real_crit_lower:
                matched_s = False
                for field in fields:
                    value = getattr(po, field)
                    # make sure that string are in unicode
                    if isinstance(value, str):
                        value = unicode(value,'unicode-escape')
                    if value and value.lower().find(s) != -1:
                        if not matched_s:
                            criteria_matched += 1
                            matched_s = True

                        tmpvalues.append(value)


            if len(tmpvalues) > 0:
                if criteria_matched not in sorted_lists: sorted_lists[criteria_matched] = []
                sorted_lists[criteria_matched].append((po, tmpvalues))


        # close our rpmdb connection so we can ctrl-c, kthxbai
        self.closeRpmDB()

        yielded = {}
        for val in reversed(sorted(sorted_lists)):
            for (po, matched) in sorted(sorted_lists[val], key=operator.itemgetter(0)):
                if (po.name, po.arch) not in yielded:
                    yield (po, matched)
                    if not showdups:
                        yielded[(po.name, po.arch)] = 1


    def _checkSignatures(self,pkgs,callback):
        ''' The the signatures of the downloaded packages '''
        # This can be overloaded by a subclass.

        for po in pkgs:
            result, errmsg = self.sigCheckPkg(po)
            if result == 0:
                # Verified ok, or verify not req'd
                continue
            elif result == 1:
                self.getKeyForPackage(po, fullaskcb=self._fullAskForGPGKeyImport)
            else:
                raise yum.Errors.YumGPGCheckError, errmsg

        return 0

    def _fullAskForGPGKeyImport(self, data):
        self.missingGPGKey = data

        raise GPGKeyNotImported()

    def _askForGPGKeyImport(self, po, userid, hexkeyid):
        '''
        Ask for GPGKeyImport
        '''
        return False

    def _removePoFromTransaction(self,po):
        '''
        Overridden so we can keep track of the package objects as they
        are removed from a transaction when skip_broken is used.
        '''
        skipped = yum.YumBase._removePoFromTransaction(self, po)
        self.skipped_packages.extend(skipped)

        return skipped

if __name__ == '__main__':
    loop = dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus(mainloop=loop)
    bus_name = dbus.service.BusName(PACKAGEKIT_DBUS_SERVICE, bus=bus)
    manager = PackageKitYumBackend(bus_name, PACKAGEKIT_DBUS_PATH)

