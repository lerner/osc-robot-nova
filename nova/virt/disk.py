# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
#
# Copyright 2011, Piston Cloud Computing, Inc.
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
Utility methods to resize, repartition, and modify disk images.

Includes injection of SSH PGP keys into authorized_keys file.

"""

import json
import os

from nova import flags
from nova import log as logging
from nova import utils
from nova.virt.injector import GuestFsInjector
from nova.virt.netcfg import NetConfig


LOG = logging.getLogger('nova.compute.disk')
FLAGS = flags.FLAGS
flags.DEFINE_integer('minimum_root_size', 1024 * 1024 * 1024 * 10,
                     'minimum size in bytes of root partition')
flags.DEFINE_integer('block_size', 1024 * 1024 * 256,
                     'block_size to use for dd')
flags.DEFINE_integer('timeout_nbd', 10,
                     'time to wait for a NBD device coming up')
flags.DEFINE_integer('max_nbd_devices', 16,
                     'maximum number of possible nbd devices')


def extend(image, size):
    """Increase image to size"""
    file_size = os.path.getsize(image)
    if file_size >= size:
        return
    utils.execute('truncate', '-s', size, image)
    # NOTE(vish): attempts to resize filesystem
    utils.execute('e2fsck', '-fp', image, check_exit_code=False)
    utils.execute('resize2fs', image, check_exit_code=False)


def inject_data(image, key=None, nets=None, metadata=None, injected_files=None):
    """Injects a ssh key and optionally net data into a disk image.

    It will use GuestFS to inject files.
    """
    with GuestFsInjector(image) as injector:
        inject_data_into_fs(injector, key, nets, metadata, injected_files)


def inject_data_into_fs(injector, key=None, nets=None, metadata=None, injected_files=None):
    """Injects data into a root filesystem using injector.
    """
    if injected_files and len(injected_files):
        _inject_files_into_fs(injected_files, injector)
    if key:
        _inject_key_into_fs(key, injector)
    if nets and len(nets):
        _inject_net_into_fs(nets, injector)
    if metadata:
        _inject_metadata_into_fs(metadata, injector)


def _inject_metadata_into_fs(metadata, injector):
    metadata = dict([(m.key, m.value) for m in metadata])
    metadata_str = json.dumps(metadata)
    injector.write('meta.js', metadata_str)

def _inject_key_into_fs(key, injector):
    """Add the given public ssh key to root's authorized_keys.

    key is an ssh key string.
    injector is used to insert files.
    """
    sshdir = '/root/.ssh'
    injector.mkdir_p(sshdir)
    injector.chmod(sshdir, 0o700)
    keyfile = os.path.join(sshdir, 'authorized_keys')
    injector.write_append(keyfile, '\n# Injected by Nova key\n' + key.strip() + '\n')


def _inject_net_into_fs(nets, injector):
    """Inject /etc/network/interfaces into the filesystem use injector.

    net is the contents of /etc/network/interfaces.
    """
    os_type = injector.get_os_type()
    nc = NetConfig(os_type)
    for cfg_name, content in nc.generate(nets):
        injector.mkdir_p(os.path.dirname(cfg_name))
        injector.write(cfg_name, content)

def _inject_files_into_fs(injected_files, injector):
    for name, content in injected_files:
        injector.mkdir_p(os.path.dirname(name))
        injector.write(name, content)
