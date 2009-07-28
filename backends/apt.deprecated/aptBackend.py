#
# vim: ts=4 et sts=4
#
# Copyright (C) 2007 Ali Sabil <ali.sabil@gmail.com>
# Copyright (C) 2007 Tom Parker <palfrey@tevp.net>
#
# Licensed under the GNU General Public License Version 2
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

import sys
import os
import re

from packagekit.backend import *
import apt_pkg,apt_inst

import warnings
warnings.filterwarnings(action='ignore', category=FutureWarning)
import apt
from aptsources.distro import get_distro
from aptsources.sourceslist import SourcesList
from sets import Set
from os.path import join,exists
from urlparse import urlparse
from apt.debfile import DebPackage
from os import system

class Package(apt.Package):
    def __str__(self):
        return "Package %s, version %s"%(self.name,self._version)

    def _cmp_deps(self,deps, version):
        for (v,c) in deps:
            if not apt_pkg.CheckDep(version,c,v):
                return False
        return True

    def __init__(self, backend, pkg, data="",version=[]):
        apt.package.Package.__init__(self, pkg._cache, pkg._depcache,
                                     pkg._records, pkg._list, pkg._pcache,
                                     pkg._pkg)
        self._version = version
        self._data = data
        self._backend = backend
        wanted_ver = None
        if self.installedVersion!=None and self._cmp_deps(version,self.installedVersion):
            wanted_ver = self.installedVersion
        elif self.installedVersion == None and version == []:
            #self.markInstall(False,False)
            wanted_ver = self.candidateVersion

        for ver in pkg._pkg.VersionList:
            #print "vers",dir(ver),version,ver
            #print data
            if (wanted_ver == None or wanted_ver == ver.VerStr) and self._cmp_deps(version,ver.VerStr):
                f, index = ver.FileList.pop(0)
                if self._data == "":
                    if f.Origin=="" and f.Archive=="now":
                        self._data = "local_install"
                    elif f.Origin!="" or f.Archive!="":
                        self._data = "%s/%s"%(f.Origin.replace("/","_"),f.Archive.replace("/","_"))
                    else:
                        self._data = "%s/unknown"%f.Site
                self._version = ver.VerStr
                break
        else:
            print "wanted",wanted_ver
            for ver in pkg._pkg.VersionList:
                print "vers",version,ver.VerStr
            backend.error(ERROR_PACKAGE_NOT_FOUND, "Can't find version %s for %s"%(version,self.name))

    def setVersion(self,version,compare="="):
        if version!=None and (self.installedVersion == None or not apt_pkg.CheckDep(version,compare,self.installedVersion)):
            self.markInstall(False,False)
            if self.candidateVersion != version:
                if self._data == "":
                    for ver in pkg._pkg.VersionList:
                        f, index = ver.FileList.pop(0)
                        self._data = "%s/%s"%(f.Origin,f.Archive)
                        if ver.VerStr == version:
                            break

                # FIXME: this is a nasty hack, assuming that the best way to resolve
                # deps for non-default repos is by switching the default release.
                # We really need a better resolver (but that's hard)
                assert self._data!=""
                origin = self._data[self._data.find("/")+1:]
                print "origin",origin
                name = self.name
                apt_pkg.Config.Set("APT::Default-Release",origin)
                if not self._backend._caches.has_key(origin):
                    self._backend._caches[origin] = apt.Cache(PackageKitProgress(self))
                    print "new cache for %s"%origin
                self.__setParent(self._backend._caches[origin][name])
                self.markInstall(False,False)
                if not apt_pkg.CheckDep(self.candidateVersion,compare,version):
                    self._backend.error(ERROR_PACKAGE_NOT_FOUND,
                            "Unable to locate package version %s (only got %s) for %s"%(version,self.candidateVersion,name))
                    return
                self.markKeep()

    @property
    def group(self):
        section = self.section.split('/')[-1].lower()
        #if section in ():
        #    return GROUP_ACCESSIBILITY
        if section in ('utils',):
            return "accessories"
        #if section in ():
        #    return GROUP_EDUCATION
        if section in ('games',):
            return "games"
        if section in ('graphics',):
            return "graphics"
        if section in ('net', 'news', 'web', 'comm'):
            return "internet"
        if section in ('editors', 'tex'):
            return "office"
        if section in ('misc',):
            return "other"
        if section in ('devel', 'libdevel', 'interpreters', 'perl', 'python'):
            return "programming"
        if section in ('sound',):
            return "multimedia"
        if section in ('base', 'admin'):
            return "system"
        return "unknown"

    @property
    def isInstalled(self):
        return super(self.__class__,self).isInstalled and self.installedVersion == self._version

    @property
    def isDevelopment(self):
        name = self.name.lower()
        section = self.section.split('/')[-1].lower()
        return name.endswith('-dev') or name.endswith('-dbg') or \
                section in ('devel', 'libdevel')

    @property
    def isGui(self):
        section = self.section.split('/')[-1].lower()
        return section in ('x11', 'gnome', 'kde')

    _HYPHEN_PATTERN = re.compile(r'(\s|_)+')

    def matchName(self, name):
        needle = name.strip().lower()
        haystack = self.name.lower()
        needle = Package._HYPHEN_PATTERN.sub('-', needle)
        haystack = Package._HYPHEN_PATTERN.sub('-', haystack)
        if haystack.find(needle) >= 0:
            return True
        return False

    def matchDetails(self, details):
        if self.matchName(details):
            return True
        needle = details.strip().lower()
        haystack = self.description.lower()
        if haystack.find(needle) >= 0:
            return True
        return False

    def matchGroup(self, name):
        needle = name.strip().lower()
        haystack = self.group
        if haystack.startswith(needle):
            return True
        return False

class PackageKitProgress(apt.progress.OpProgress, apt.progress.FetchProgress):
    def __init__(self, backend):
        self._backend = backend
        apt.progress.OpProgress.__init__(self)
        apt.progress.FetchProgress.__init__(self)

    # OpProgress callbacks
    def update(self, percent):
        pass

    def done(self):
        pass

    # FetchProgress callbacks
    def pulse(self):
        apt.progress.FetchProgress.pulse(self)
        self._backend.percentage(self.percent)
        return True

    def stop(self):
        self._backend.percentage(100)

    def mediaChange(self, medium, drive):
        # This probably should not be an error, but a Message.
        self._backend.error(ERROR_UNKNOWN,
                "Medium change needed")

class PackageKitAptBackend(PackageKitBaseBackend):
    def __init__(self, args):
        PackageKitBaseBackend.__init__(self, args)
        self.status(STATUS_SETUP)
        self._caches  = {}
        self._apt_cache = apt.Cache(PackageKitProgress(self))
        default = apt_pkg.Config.Find("APT::Default-Release")
        if default=="":
            d = get_distro()
            if d.id == "Debian":
                default = "stable"
            elif d.id == "Ubuntu":
                default = "main"
            else:
                raise Exception,d.id

        self._caches[default] = self._apt_cache


    def search_name(self, filters, key):
        '''
        Implement the {backend}-search-name functionality
        '''
        self.status(STATUS_INFO)
        self.allow_cancel(True)
        for package in self._do_search(filters,
                lambda pkg: pkg.matchName(key)):
            self._emit_package(package)

    def search_details(self, filters, key):
        '''
        Implement the {backend}-search-details functionality
        '''
        self.status(STATUS_INFO)
        self.allow_cancel(True)
        for package in self._do_search(filters,
                lambda pkg: pkg.matchDetails(key)):
            self._emit_package(package)

    def search_group(self, filters, key):
        '''
        Implement the {backend}-search-group functionality
        '''
        self.status(STATUS_INFO)
        self.allow_cancel(True)
        for package in self._do_search(filters,
                lambda pkg: pkg.matchGroup(key)):
            self._emit_package(package)

    def search_file(self, filters, key):
        '''
        Implement the {backend}-search-file functionality
        '''
        self.allow_cancel(True)
        self.percentage(None)

        self.error(ERROR_NOT_SUPPORTED,
                "This function is not implemented in this backend")

    def refresh_cache(self):
        '''
        Implement the {backend}-refresh_cache functionality
        '''
        self.status(STATUS_REFRESH_CACHE)
        try:
            res = self._apt_cache.update(PackageKitProgress(self))
        except Exception, error_message:
             self.error(ERROR_UNKNOWN,
                        "Failed to fetch the following items:\n%s" % error_message)
        return res

    def get_details(self, package):
        '''
        Implement the {backend}-get-details functionality
        '''
        self.status(STATUS_INFO)
        name, version, arch, data = self.get_package_from_id(package)
        pkg = Package(self, self._apt_cache[name])
        description = re.sub('\s+', ' ', pkg.description).strip()
        self.description(package, 'unknown', pkg.group, description,
                         pkg.architecture, pkg.packageSize)

    def resolve(self, name):
        '''
        Implement the {backend}-resolve functionality
        '''
        self.status(STATUS_INFO)
        try:
            pkg = Package(self,self._apt_cache[name])
            self._emit_package(pkg)
        except KeyError:
            self.error(ERROR_PACKAGE_NOT_FOUND,"Can't find a package called '%s'"%name)

    def _do_deps(self,inp,deps,recursive):
        inp.markInstall()
        newkeys = []
        for x in inp.candidateDependencies:
            n = x.or_dependencies[0].name
            if not deps.has_key(n):
                deps[n] = []
                newkeys.append(n)
            deps[n].append((x.or_dependencies[0].version,x.or_dependencies[0].relation))
        if recursive:
            for n in newkeys:
                try:
                    deps = self._do_deps(Package(self,self._apt_cache[n],version=deps[n]),deps,recursive)
                except KeyError: # FIXME: we're assuming this is a virtual package, which we can't cope with yet
                    del deps[n]
                    continue
        return deps

    def get_depends(self,filters,package, recursive):
        '''
        Implement the {backend}-get-depends functionality
        '''
        self.allow_cancel(True)
        self.status(STATUS_INFO)
        recursive = (recursive == "True")
        name, version, arch, data = self.get_package_from_id(package)
        pkg = Package(self,self._apt_cache[name],version=[(version,"=")],data=data)
        pkg.setVersion(version)
        deps = self._do_deps(pkg, {}, recursive)
        for n in deps.keys():
           self._emit_package(Package(self,self._apt_cache[n],version=deps[n]))

    def _do_reqs(self,inp,pkgs,recursive):
        extra = []
        fails = []
        for r in inp._pkg.RevDependsList:
            ch = apt_pkg.CheckDep(inp._version,r.CompType,r.TargetVer)
            v = (r.ParentPkg.Name,r.ParentVer.VerStr)
            if not ch or v in fails:
                #print "skip",r.TargetVer,r.CompType,r.ParentPkg.Name,r.ParentVer.VerStr
                fails.append(v)
                continue
            p = Package(self,self._apt_cache[r.ParentPkg.Name],r.ParentVer.VerStr)
            if v not in pkgs:
                extra.append(p)
                #print "new pkg",p
                self._emit_package(p)
            pkgs.add(v)
        if recursive:
            for e in extra:
                pkgs = self._do_reqs(p, pkgs,recursive)
        return pkgs

    def get_requires(self,package,recursive):
        '''
        Implement the {backend}-get-requires functionality
        '''
        self.allow_cancel(True)
        self.status(STATUS_INFO)
        recursive = (recursive == "True")
        name, version, arch, data = self.get_package_from_id(package)
        pkg = Package(self,self._apt_cache[name], version=[(version,"=")], data=data)

        pkgs = Set()
        self._do_reqs(pkg,pkgs, recursive)

    def _build_repo_list(self):
        repo = {}

        sources = SourcesList()
        repo["__sources"] = sources

        root = apt_pkg.Config.FindDir("Dir::State::Lists")
        #print root
        for entry in sources:
            if entry.type!="":
                url = entry.uri
                #if entry.template!=None:
                url +="/dists/"
                url += entry.dist
                url = url.replace("//dists","/dists")
                #print url
                path = join(root,"%s_Release"%(apt_pkg.URItoFileName(url)))
                if not exists(path):
                    #print path
                    name = "%s/unknown"%urlparse(entry.uri)[1]
                else:
                    lines = file(path).readlines()
                    origin = ""
                    suite = ""
                    for l in lines:
                        if l.find("Origin: ")==0:
                            origin = l.split(" ",1)[1].strip()
                        elif l.find("Suite: ")==0:
                            suite = l.split(" ",1)[1].strip()
                    assert origin!="" and suite!=""
                    name = "%s/%s"%(origin,suite)
                if entry.type == "deb-src":
                    name += "-src"

                repo[name] = {"entry":entry}
        return repo

    def get_repo_list(self, filters):
        '''
        Implement the {backend}-get-repo-list functionality
        '''
        self.allow_interrupt(True)
        self.status(STATUS_INFO)
        repo = self._build_repo_list()
        for e in repo.keys():
            if e == "__sources":
                continue
            self.repo_detail(repo[e]["entry"].line.strip(),e,not repo[e]["entry"].disabled)

    def repo_enable(self, repoid, enable):
        '''
        Implement the {backend}-repo-enable functionality
        '''
        enable = (enable == "True")
        repo = self._build_repo_list()
        if not repo.has_key(repoid):
            self.error(ERROR_REPO_NOT_FOUND,"Couldn't find repo '%s'"%repoid)
            return
        r = repo[repoid]
        if not r["entry"].disabled == enable: # already there
            return
        r["entry"].set_enabled(enable)
        try:
            repo["__sources"].save()
        except IOError,e:
            self.error(ERROR_UNKNOWN, "Problem while trying to save repo settings to %s: %s"%(e.filename,e.strerror))

    def get_updates(self, filter):
        self._apt_cache.upgrade(False)
        for pkg in self._apt_cache.getChanges():
            self._emit_package(Package(self, pkg))

    def get_update_detail(self, package):
        self.allow_cancel(True)
        self.percentage(None)
        self.status(STATUS_INFO)
        name, version, arch, data = self.get_package_from_id(package)
        update = ""
        obsolete = ""
        cve_url = ""
        bz_url = ""
        vendor_url = ""
        reboot = "none"
        desc = self._apt_cache[name].description
        self.update_detail(package,update,obsolete,vendor_url,bz_url,cve_url,reboot,desc)


    def install_files (self, inst_files):
        '''
        Implement the {backend}-install_files functionality
        Install the package containing the inst_file file
        '''
        if not exists(inst_file):
            self.error(ERROR_PACKAGE_NOT_FOUND,"Can't find %s"%inst_file)
            return
        deb = DebPackage(inst_file)
        deps = {}
        for k in ["Depends","Recommends"]:
            if not deb._sections.has_key(k):
                continue
            for items in apt_pkg.ParseDepends(deb[k]):
                assert len(items) == 1,"Can't handle or deps properly yet"
                (pkg,ver,comp) = items[0]
                if not deps.has_key(pkg):
                    deps[pkg] = []
                deps[pkg].append((ver,comp))
        for n in deps.keys():
           p = Package(self,self._apt_cache[n],version=deps[n])
           if not p.isInstalled:
               p.markInstall()
        assert self._apt_cache.getChanges()==[],"Don't handle install changes yet"
        # FIXME: nasty hack. Need a better way in
        ret = system("dpkg -i %s"%inst_file)
        if ret!=0:
            self.error(ERROR_UNKNOWN,"Can't install package")

    ### Helpers ###
    def _emit_package(self, package):
        id = self.get_package_id(package.name,
                package._version,
                package.architecture,
                package._data)
        if package.isInstalled:
            status = INFO_INSTALLED
        else:
            status = INFO_AVAILABLE
        summary = package.summary
        self.package(id, status, summary)

    def _do_search(self, filters, condition):
        filters = filters.split(';')
        size = len(self._apt_cache)
        percentage = 0
        for i, pkg in enumerate(self._apt_cache):
            new_percentage = i / float(size) * 100
            if new_percentage - percentage >= 5:
                percentage = new_percentage
                self.percentage(percentage)
            package = Package(self, pkg)
            if package.installedVersion is None and \
                    package.candidateVersion is None:
                continue
            if not condition(package):
                continue
                continue
            vers = [x.VerStr for x in package._pkg.VersionList]
            if package.installedVersion!=None:
                i = package.installedVersion
                if i in vers and vers[0]!=i:
                    del vers[vers.index(i)]
                    vers.insert(0,i)

            for ver in vers:
                p = Package(self, package, version=[[ver,"="]])
                if self._do_filtering(p, filters):
                    yield p
        self.percentage(100)

    def _do_filtering(self, package, filters):
        if len(filters) == 0 or filters == ['none']:
            return True
        if (FILTER_INSTALLED in filters) and (not package.isInstalled):
            return False
        if (FILTER_NOT_INSTALLED in filters) and package.isInstalled:
            return False
        if (FILTER_GUI in filters) and (not package.isGui):
            return False
        if (FILTER_NOT_GUI in filters) and package.isGui:
            return False
        if (FILTER_DEVELOPMENT in filters) and (not package.isDevelopment):
            return False
        if (FILTER_NOT_DEVELOPMENT in filters) and package.isDevelopment:
            return False
        return True
