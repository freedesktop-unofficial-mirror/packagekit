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

# Copyright (C) 2007 Tim Lauridsen <timlau@fedoraproject.org>

#
# This file contain the base classes to implement a PackageKit python backend
#

# imports
import sys
import codecs
import traceback
import locale

sys.stdout = codecs.getwriter('utf-8')(sys.stdout)

from enums import *

# Classes

class PackageKitBaseBackend:

    def __init__(self,cmds):
        # Setup a custom exception handler
        installExceptionHandler(self)
        self.cmds = cmds
        self._locked = False

    def doLock(self):
        ''' Generic locking, overide and extend in child class'''
        self._locked = True

    def unLock(self):
        ''' Generic unlocking, overide and extend in child class'''
        self._locked = False

    def isLocked(self):
        return self._locked

    def percentage(self,percent=None):
        '''
        Write progress percentage
        @param percent: Progress percentage
        '''
        if percent != None:
            print "percentage\t%i" % (percent)
        else:
            print "no-percentage-updates"
        sys.stdout.flush()

    def sub_percentage(self,percent=None):
        '''
        send 'subpercentage' signal : subprogress percentage
        @param percent: subprogress percentage
        '''
        print "subpercentage\t%i" % (percent)
        sys.stdout.flush()

    def error(self,err,description,exit=True):
        '''
        send 'error'
        @param err: Error Type (ERROR_NO_NETWORK, ERROR_NOT_SUPPORTED, ERROR_INTERNAL_ERROR)
        @param description: Error description
        @param exit: exit application with rc=1, if true
        '''
        print "error\t%s\t%s" % (err,description)
        sys.stdout.flush()
        if exit:
            if self.isLocked():
                self.unLock()
            sys.exit(1)
    
    def message(self,typ,msg):
        '''
        send 'message' signal
        @param typ: MESSAGE_WARNING, MESSAGE_NOTICE, MESSAGE_DEAMON
        '''
        print "message\t%s\t%s" % (typ,msg)
        sys.stdout.flush()

    def package(self,id,status,summary):
        '''
        send 'package' signal
        @param info: the enumerated INFO_* string
        @param id: The package ID name, e.g. openoffice-clipart;2.6.22;ppc64;fedora
        @param summary: The package Summary
        '''
        print >> sys.stdout,"package\t%s\t%s\t%s" % (status,id,summary)
        sys.stdout.flush()

    def status(self,state):
        '''
        send 'status' signal
        @param state: STATUS_DOWNLOAD, STATUS_INSTALL, STATUS_UPDATE, STATUS_REMOVE, STATUS_WAIT
        '''
        print "status\t%s" % (state)
        sys.stdout.flush()

    def repo_detail(self,repoid,name,state):
        '''
        send 'repo-detail' signal
        @param repoid: The repo id tag
        @param state: false is repo is disabled else true.
        '''
        print >> sys.stdout,"repo-detail\t%s\t%s\t%s" % (repoid,name,state)
        sys.stdout.flush()

    def data(self,data):
        '''
        send 'data' signal:
        @param data:  The current worked on package
        '''
        print "data\t%s" % (data)
        sys.stdout.flush()

    def description(self,id,license,group,desc,url,bytes):
        '''
        Send 'description' signal
        @param id: The package ID name, e.g. openoffice-clipart;2.6.22;ppc64;fedora
        @param license: The license of the package
        @param group: The enumerated group
        @param desc: The multi line package description
        @param url: The upstream project homepage
        @param bytes: The size of the package, in bytes
        '''
        print >> sys.stdout,"description\t%s\t%s\t%s\t%s\t%s\t%ld" % (id,license,group,desc,url,bytes)
        sys.stdout.flush()

    def files(self, id, file_list):
        '''
        Send 'files' signal
        @param file_list: List of the files in the package, separated by ';'
        '''
        print >> sys.stdout,"files\t%s\t%s" % (id, file_list)
        sys.stdout.flush()

    def update_detail(self,id,updates,obsoletes,vendor_url,bugzilla_url,cve_url,restart,update_text):
        '''
        Send 'updatedetail' signal
        @param id: The package ID name, e.g. openoffice-clipart;2.6.22;ppc64;fedora
        @param updates:
        @param obsoletes:
        @param vendor_url:
        @param bugzilla_url:
        @param cve_url:
        @param restart:
        @param update_text:
        '''
        print >> sys.stdout,"updatedetail\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (id,updates,obsoletes,vendor_url,bugzilla_url,cve_url,restart,update_text)
        sys.stdout.flush()

    def require_restart(self,restart_type,details):
        '''
        Send 'requirerestart' signal
        @param restart_type: RESTART_SYSTEM, RESTART_APPLICATION,RESTART_SESSION
        @param details: Optional details about the restart
        '''
        print "requirerestart\t%s\t%s" % (restart_type,details)
        sys.stdout.flush()

    def allow_cancel(self,allow):
        '''
        send 'allow-cancel' signal:
        @param allow:  Allow the current process to be aborted.
        '''
        if allow:
            data = 'true'
        else:
            data = 'false'
        print "allow-cancel\t%s" % (data)
        sys.stdout.flush()

    def repo_signature_required(self,id,repo_name,key_url,key_userid,key_id,key_fingerprint,key_timestamp,type):
        '''
        send 'repo-signature-required' signal:
        @param id:           Id of the package needing a signature
        @param repo_name:       Name of the repository
        @param key_url:         URL which the user can use to verify the key
        @param key_userid:      Key userid
        @param key_id:          Key ID
        @param key_fingerprint: Full key fingerprint
        @param key_timestamp:   Key timestamp
        @param type:            Key type (GPG)
        '''
        print "repo-signature-required\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s" % (
            id,repo_name,key_url,key_userid,key_id,key_fingerprint,key_timestamp,type
            )
        sys.stdout.flush()

    def get_package_id(self,name,version,arch,data):
        return "%s;%s;%s;%s" % (name,version,arch,data)

    def get_package_from_id(self,id):
        ''' split up a package id name;ver;arch;data into a tuple
            containing (name,ver,arch,data)
        '''
        return tuple(id.split(';', 4))

    def check_license_field(self,license_field):
        '''
        Check the string license_field for free licenses, indicated by
        their short names as documented at
        http://fedoraproject.org/wiki/Licensing

        Licenses can be grouped by " or " to indicate that the package
        can be redistributed under any of the licenses in the group.
        For instance: GPLv2+ or Artistic or FooLicense.

        Also, if a license ends with "+", the "+" is removed before
        comparing it to the list of valid licenses.  So if license
        "FooLicense" is free, then "FooLicense+" is considered free.

        Groups of licenses can be grouped with " and " to indicate
        that parts of the package are distributed under one group of
        licenses, while other parts of the package are distributed
        under another group.  Groups may be wrapped in parenthesis.
        For instance:
          (GPLv2+ or Artistic) and (GPL+ or Artistic) and FooLicense.

        At least one license in each group must be free for the
        package to be considered Free Software.  If the license_field
        is empty, the package is considered non-free.
        '''

        groups = license_field.split(" and ")

        if len(groups) == 0:
            return False

        one_free_group = False

        for group in groups:
            group = group.replace("(","")
            group = group.replace(")","")
            licenses = group.split(" or ")

            group_is_free = False

            for license in licenses:
                license = license.strip()

                if len(license) < 1:
                    continue

                if license[-1] == "+":
                    license = license[0:-1]

                if license in PackageKitEnum.free_licenses:
                    one_free_group = True
                    group_is_free = True
                    break

            if group_is_free == False:
                return False

        if one_free_group == False:
            return False

        return True

#
# Backend Action Methods
#

    def search_name(self,filters,key):
        '''
        Implement the {backend}-search-name functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def search_details(self,filters,key):
        '''
        Implement the {backend}-search-details functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def search_group(self,filters,key):
        '''
        Implement the {backend}-search-group functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def search_file(self,filters,key):
        '''
        Implement the {backend}-search-file functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def get_update_detail(self,package):
        '''
        Implement the {backend}-get-update-detail functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def get_depends(self,filters,package,recursive):
        '''
        Implement the {backend}-get-depends functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def get_requires(self,filters,package,recursive):
        '''
        Implement the {backend}-get-requires functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def what_provides(self,filters,provides_type,search):
        '''
        Implement the {backend}-what-provides functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def update_system(self):
        '''
        Implement the {backend}-update-system functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def refresh_cache(self):
        '''
        Implement the {backend}-refresh_cache functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def install(self, package):
        '''
        Implement the {backend}-install functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def install_file (self, inst_file):
        '''
        Implement the {backend}-install_file functionality
        Install the package containing the inst_file file
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def service_pack (self, location):
        '''
        Implement the {backend}-service-pack functionality
        Update the computer from a service pack in location
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def resolve(self, name):
        '''
        Implement the {backend}-resolve functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def remove(self, allowdep, package):
        '''
        Implement the {backend}-remove functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def update(self, package):
        '''
        Implement the {backend}-update functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def get_description(self, package):
        '''
        Implement the {backend}-get-description functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def get_files(self, package):
        '''
        Implement the {backend}-get-files functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED, "This function is not implemented in this backend")

    def get_updates(self,filter):
        '''
        Implement the {backend}-get-updates functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def repo_enable(self, repoid, enable):
        '''
        Implement the {backend}-repo-enable functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def repo_set_data(self, repoid, parameter, value):
        '''
        Implement the {backend}-repo-set-data functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def get_repo_list(self, filters):
        '''
        Implement the {backend}-get-repo-list functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def repo_signature_install(self,package):        
        '''
        Implement the {backend}-repo-signature-install functionality
        Needed to be implemented in a sub class
        '''
        self.error(ERROR_NOT_SUPPORTED,"This function is not implemented in this backend")

    def customTracebackHandler(self,tb):
        '''
        Custom Traceback Handler
        this is called by the ExceptionHandler
        return True if the exception is handled in the method.
        return False if to do the default action an signal an error
        to packagekit.
        Overload this method if you what handle special Tracebacks
        '''
        return False

class PackagekitProgress:
    '''
    Progress class there controls the total progress of a transaction
    the transaction is divided in n milestones. the class contains a subpercentage
    of the current step (milestone n -> n+1) and the percentage of the whole transaction

    Usage:

    from packagekit.backend import PackagekitProgress

    steps = [10,30,50,70] # Milestones in %
    progress = PackagekitProgress()
    progress.set_steps(steps)
    for milestone in range(len(steps)):
        # do the action is this step
        for i in range(100):
            # do some action
            progress.set_subpercent(i+1)
            print "progress : %s " % progress.percent
        progress.step() # step to next milestone

    '''

    #TODO: Add support for elapsed/remaining time

    def __init__(self):
        self.percent = 0
        self.steps = []
        self.current_step = 0
        self.subpercent = 0

    def set_steps(self,steps):
        '''
        Set the steps for the whole transaction
        @param steps: list of int representing the percentage of each step in the transaction
        '''
        self.reset()
        self.steps = steps
        self.current_step = 0

    def reset(self):
        self.percent = 0
        self.steps = []
        self.current_step = 0
        self.subpercent = 0

    def step(self):
        '''
        Step to the next step in the transaction
        '''
        if self.current_step < len(self.steps)-1:
            self.current_step += 1
            self.percent = self.steps[self.current_step]
            self.subpercent = 0
        else:
            self.percent = 100
            self.subpercent = 0

    def set_subpercent(self,pct):
        '''
        Set subpercentage and update percentage
        '''
        self.subpercent = pct
        self._update_percent()

    def _update_percent(self):
        '''
        Increment percentage based on current step and subpercentage
        '''
        if self.current_step == 0:
            startpct = 0
        else:
            startpct = self.steps[self.current_step-1]
        if self.current_step < len(self.steps)-1:
            endpct = self.steps[self.current_step+1]
        else:
            endpct = 100
        deltapct = endpct -startpct
        f = float(self.subpercent)/100.0
        incr = int(f*deltapct)
        self.percent = startpct + incr


def exceptionHandler(typ, value, tb, base):
    # Restore original exception handler
    sys.excepthook = sys.__excepthook__
    # Call backend custom Traceback handler
    if not base.customTracebackHandler(typ):
        etb = traceback.extract_tb(tb)
        errmsg = 'Error Type: %s;' % str(typ)
        errmsg += 'Error Value: %s;' % str(value)
        for tub in etb:
            f,l,m,c = tub # file,lineno, function, codeline
            errmsg += '  File : %s , line %s, in %s;' % (f,str(l),m)
            errmsg += '    %s;' % c
        # send the traceback to PackageKit
        base.error(ERROR_INTERNAL_ERROR,errmsg,exit=True)


def installExceptionHandler(base):
    sys.excepthook = lambda typ, value, tb: exceptionHandler(typ, value, tb,base)

