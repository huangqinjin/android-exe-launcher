#!/usr/bin/env python3
#
# Copyright (c) 2022 Huang Qinjin (huangqinjin@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0.
#    (See accompanying file LICENSE_1_0.txt or copy at
#          https://www.boost.org/LICENSE_1_0.txt)
#

import argparse
import os
import io
import shutil
import sys
import subprocess
import tempfile
import zipfile
import configparser
import itertools
import urllib.request
from pathlib import Path
import deapexer



def cpy(dst, src, *files):
    os.makedirs(dst, exist_ok=True)
    for f in files:
        shutil.copy2(os.path.join(src, f), dst)

def copy_from_apex(src, dst):
    cpy(os.path.join(dst, 'bin'),
        os.path.join(src, 'bin'),
        'linker64')

    cpy(os.path.join(dst, 'lib64'),
        os.path.join(src, 'lib64', 'bionic'),
        'libc.so', 'libm.so', 'libdl.so',
    )


def extract_apex_and_copy(apex, dst):
    with tempfile.TemporaryDirectory() as tempdir:
        deapexer.RunExtract(argparse.Namespace(
            apex = apex,
            dest = tempdir,
            debugfs_path = '/usr/sbin/debugfs'
        ))

        copy_from_apex(tempdir, dst)


def copy_from_img(src, dst):
    linkerconfig = os.path.join(dst, 'linkerconfig')
    os.makedirs(linkerconfig, exist_ok=True)
    with open(os.path.join(linkerconfig, 'ld.config.txt'), 'ba'): pass


def mount_img_and_copy(img, dst):
    try:
        tempdir = os.path.join(dst, 'mount')
        mkdir = not os.path.isdir(tempdir)
        if mkdir:
            os.makedirs(tempdir)
        # https://unix.stackexchange.com/questions/604161/how-can-i-mount-this-disk-image
        subprocess.run(['sudo', 'mount', '-o', f"loop,ro,offset={512 * 2048 * 3}", img, tempdir])

        copy_from_img(tempdir, dst)
        extract_apex_and_copy(os.path.join(tempdir, 'system', 'apex', 'com.android.runtime.apex'), os.path.join(dst, 'system'))
    finally:
        subprocess.run(['sudo', 'umount', tempdir])
        if mkdir:
            os.rmdir(tempdir)


def load_source_properties(mod, dir):
    try:
        with mod.open(os.path.join(dir, 'source.properties'), 'r') as lines:
            if isinstance(lines, io.BufferedIOBase):
                lines = io.TextIOWrapper(lines) 
            prop = configparser.ConfigParser()
            prop.read_file(itertools.chain(('[root]',), lines))
            return prop['root']
    except FileNotFoundError:
        return {}

def lookup_system_image(sdk, abi, api):
    dir = os.path.join(sdk, 'system-images', f"android-{api}", 'google_apis', abi)
    prop = load_source_properties(__builtins__, dir)
    rev = int(prop.get('Pkg.Revision', 0))
    img = os.path.join(dir, 'system.img')
    if not os.path.isfile(img):
        img = None
    return (img, rev)


def download_system_package(dir, abi, api, rev):
    filename = f"{abi}-{api}_r{rev:02d}.zip"
    path = os.path.join(dir, filename)
    if not os.path.isfile(path):
        url = f"http://dl.google.com/android/repository/sys-img/google_apis/{filename}"
        with urllib.request.urlopen(url) as response, open(path, 'wb') as output:
            shutil.copyfileobj(response, output)
    return path

def extract_system_package(package, abi, dst):
    with zipfile.ZipFile(package, 'r') as zip:
        prop = load_source_properties(zip, abi)
        rev = int(prop.get('Pkg.Revision', 0))
        img = os.path.join(dst, abi, 'system.img')
        if rev != 0 and not os.path.isfile(img):
            img = zip.extract(os.path.join(abi, 'system.img'), dst)
        if img is not None and not os.path.isfile(img):
            img = None
        return (img, rev)

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', help='path to Android SDK root', default=None)
    parser.add_argument('--abi', help='Android system ABI', default='arm64-v8a')
    parser.add_argument('--api', help='Android system api level', required=True, type=int)
    parser.add_argument('--rev', help='Android system image revision', default=0, type=int)
    parser.add_argument('--dir', help='output directory', default='system-images')
    parser.add_argument('--version', help='package version number', default=1, type=int)

    args = parser.parse_args(argv)
    if args.sdk is None:
        args.sdk = os.getenv('ANDROID_SDK_HOME')
    if args.sdk is None:
        args.sdk = os.getenv('ANDROID_SDK_ROOT')

    args.dir =  os.path.abspath(args.dir)

    if args.sdk is not None:
        img, rev = lookup_system_image(args.sdk, args.abi, args.api)
        if rev == 0 or img == None:
            print(f"No system image {args.abi} android-{args.api} in SDK")
            img = None
        elif args.rev != 0 and args.rev != rev:
            print(f"Required system image revision is {args.rev} but {rev} in SDK")
            img = None
        if img is not None:
            args.rev = rev

    if img is None and args.rev == 0:
        print("Please provide system image revision number to download")
        sys.exit(1)

    ver = f"{args.api}_r{args.rev:02d}"

    if img is None:
        print("Downloading package...")
        package = download_system_package(args.dir, args.abi, args.api, args.rev)
        print("Extracting package...")
        img, rev = extract_system_package(package, args.abi, os.path.join(args.dir, f"android-{ver}"))
        if args.rev != rev or img == None:
            print("Download/Extract system package failed")
            sys.exit(1)

    dst = os.path.join(args.dir, f"android-{ver}", args.abi)
    print("Mounting image and copying...")
    mount_img_and_copy(img, dst)
    print(f"Successfully copied to {dst}")
    
    if args.version >= 0:
        print("Generating NuGet package...")
        src = os.path.dirname(os.path.realpath(__file__))
        for f in ['README.md', 'android-exe-launcher.nuspec']:
            Path(dst, f).write_text(Path(src, f).read_text().format(**vars(args)))

        nuget = os.path.join(args.dir, 'nuget.exe')
        if not os.path.isfile(nuget):
            url = 'https://dist.nuget.org/win-x86-commandline/latest/nuget.exe'
            with urllib.request.urlopen(url) as response, open(nuget, 'wb') as output:
                shutil.copyfileobj(response, output)
        
        subprocess.run(['wine64', nuget, 'pack'], cwd = dst)

if __name__ == '__main__':
    main(sys.argv[1:])
