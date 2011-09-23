# -*- coding: utf-8 -*-
#
# Copyright © 2011 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public
# License as published by the Free Software Foundation; either version
# 2 of the License (GPLv2) or (at your option) any later version.
# There is NO WARRANTY for this software, express or implied,
# including the implied warranties of MERCHANTABILITY,
# NON-INFRINGEMENT, or FITNESS FOR A PARTICULAR PURPOSE. You should
# have received a copy of GPLv2 along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.

import atexit
import os
import shutil
import string
import sys
import traceback
import tempfile
from pprint import pprint

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../common')))

import testutil

from pulp.server.content import loader
from pulp.server.content.plugins.distributor import Distributor
from pulp.server.content.plugins.importer import Importer

# test data and data generation api --------------------------------------------

_generated_paths = []


def _delete_generated_paths():
    for p in _generated_paths:
        if p in sys.path:
            sys.path.remove(p)
        shutil.rmtree(p)


#atexit.register(_delete_generated_paths)

# test file(s) generation

def gen_plugin_root():
    path = tempfile.mkdtemp()
    sys.path.insert(0, path)
    _generated_paths.append(path)
    return path


_PLUGIN_TEMPLATE = string.Template('''
from pulp.server.content.plugins.$BASE_NAME import $BASE_TITLE
class $PLUGIN_TITLE($BASE_TITLE):
    @classmethod
    def metadata(cls):
        data = {'name': '$PLUGIN_NAME',
                'types': $TYPE_LIST}
        return data
''')

_CONF_TEMPLATE = string.Template('''
{"enabled": $ENABLED}
''')


def gen_plugin(root, type_, name, types, enabled=True):
    base_name = type_.lower()
    base_title = type_.title()
    plugin_name = name.lower()
    plugin_title = name
    type_list = '[%s]' % ', '.join('\'%s\'' % t for t in types)
    # create the directory
    plugin_dir = os.path.join(root, '%ss' % base_name, plugin_name)
    os.makedirs(plugin_dir)
    # write the package module
    pck_name = os.path.join(plugin_dir, '__init__.py')
    handle = open(pck_name, 'w')
    handle.write('\n')
    handle.close()
    # write the plugin module
    contents = _PLUGIN_TEMPLATE.safe_substitute({'BASE_NAME': base_name,
                                                 'BASE_TITLE': base_title,
                                                 'PLUGIN_TITLE': plugin_title,
                                                 'PLUGIN_NAME': plugin_name,
                                                 'TYPE_LIST': type_list})
    mod_name = os.path.join(plugin_dir, '%s.py' % base_name)
    handle = open(mod_name, 'w')
    handle.write(contents)
    handle.close()
    # write plugin config
    contents = _CONF_TEMPLATE.safe_substitute({'ENABLED': str(enabled).lower()})
    cfg_name = os.path.join(plugin_dir, '%s.conf' % plugin_name)
    handle = open(cfg_name, 'w')
    handle.write(contents)
    handle.close()
    # return the top level directory
    return os.path.join(root, '%ss' % base_name)

# test classes

class WebDistributor(Distributor):
    @classmethod
    def metadata(cls):
        return {'types': ['http', 'https']}

class ExcellentImporter(Importer):
    @classmethod
    def metadata(cls):
        return {'types': ['excellent_type']}


class BogusImporter(Importer):
    @classmethod
    def metadata(cls):
        return {'types': ['excellent_type']}

# unit tests -------------------------------------------------------------------

class PluginMapTests(testutil.PulpTest):

    def setUp(self):
        super(PluginMapTests, self).setUp()
        self.plugin_map = loader._PluginMap()

    def test_add_plugin(self):
        name = 'excellent'
        types = ExcellentImporter.metadata()['types']
        self.plugin_map.add_plugin(name, ExcellentImporter, {}, types)
        self.assertTrue(name in self.plugin_map.configs)
        self.assertTrue(name in self.plugin_map.plugins)
        self.assertTrue(name in self.plugin_map.types)

    def test_add_disabled(self):
        name = 'disabled'
        cfg = {'enabled': False}
        self.plugin_map.add_plugin(name, BogusImporter, cfg)
        self.assertFalse(name in self.plugin_map.configs)
        self.assertFalse(name in self.plugin_map.plugins)
        self.assertFalse(name in self.plugin_map.types)

    def test_conflicting_names(self):
        name = 'less_excellent'
        types = ExcellentImporter.metadata()['types']
        self.plugin_map.add_plugin(name, ExcellentImporter, {}, types)
        self.assertRaises(loader.ConflictingPluginName,
                          self.plugin_map.add_plugin,
                          name, BogusImporter, {}, types)

    def test_conflicting_types(self):
        types = ExcellentImporter.metadata()['types']
        self.plugin_map.add_plugin('excellent', ExcellentImporter, {}, types)
        types = BogusImporter.metadata()['types']
        self.assertRaises(loader.ConflictingPluginTypes,
                          self.plugin_map.add_plugin,
                          'bogus', BogusImporter, {}, types)

    def test_get_plugin_by_name(self):
        name = 'excellent'
        self.plugin_map.add_plugin(name, ExcellentImporter, {})
        cls = self.plugin_map.get_plugin_by_name(name)[0]
        self.assertIs(cls, ExcellentImporter)

    def test_get_plugin_by_type(self):
        types = ExcellentImporter.metadata()['types']
        self.plugin_map.add_plugin('excellent', ExcellentImporter, {}, types)
        cls = self.plugin_map.get_plugin_by_type(types[0])[0]
        self.assertIs(cls, ExcellentImporter)

    def test_name_not_found(self):
        self.assertRaises(loader.PluginNotFound,
                          self.plugin_map.get_plugin_by_name,
                          'bogus')

    def test_type_not_found(self):
        self.assertRaises(loader.PluginNotFound,
                          self.plugin_map.get_plugin_by_type,
                          'bogus_type')

    def test_remove_plugin(self):
        name = 'excellent'
        self.plugin_map.add_plugin(name, ExcellentImporter, {})
        self.assertIn(name, self.plugin_map.plugins)
        self.plugin_map.remove_plugin(name)
        self.assertNotIn(name, self.plugin_map.plugins)


class LoaderInstanceTest(testutil.PulpTest):

    def test_loader_instantiation(self):
        try:
            l = loader.PluginLoader()
        except Exception, e:
            self.fail('\n'.join((repr(e), traceback.format_exc())))


class LoaderTest(testutil.PulpTest):

    def setUp(self):
        super(LoaderTest, self).setUp()
        self.loader = loader.PluginLoader()

    def tearDown(self):
        super(LoaderTest, self).tearDown()
        self.loader = None


class LoaderDirectOperationsTests(LoaderTest):

    def test_distributor(self):
        name = 'spidey'
        types = WebDistributor.metadata()['types']
        self.loader.add_distributor(name, WebDistributor, {})

        cls = self.loader.get_distributor_by_name(name)[0]
        self.assertIs(cls, WebDistributor)

        cls = self.loader.get_distributor_by_type(types[0])[0]
        self.assertIs(cls, WebDistributor)

        cls = self.loader.get_distributor_by_type(types[1])[0]
        self.assertIs(cls, WebDistributor)

        distributors = self.loader.get_loaded_distributors()
        self.assertIn(name, distributors)

        self.loader.remove_distributor(name)
        self.assertRaises(loader.PluginNotFound,
                          self.loader.get_distributor_by_name,
                          name)

    def test_importer(self):
        name = 'bill'
        types = ExcellentImporter.metadata()['types']
        self.loader.add_importer(name, ExcellentImporter, {})

        cls = self.loader.get_importer_by_name(name)[0]
        self.assertIs(cls, ExcellentImporter)

        cls = self.loader.get_importer_by_type(types[0])[0]
        self.assertIs(cls, ExcellentImporter)

        importers = self.loader.get_loaded_importers()
        self.assertIn(name, importers)

        self.loader.remove_importer(name)
        self.assertRaises(loader.PluginNotFound,
                          self.loader.get_importer_by_name,
                          name)


class LoaderFileSystemOperationsTests(LoaderTest):

    def test_single_distributor(self):
        plugin_root = gen_plugin_root()
        print plugin_root
        types = ['test_type']
        distributors_root = gen_plugin(plugin_root,
                                       'distributor',
                                       'TestDistributor',
                                       types)
        print distributors_root
        self.loader.load_distributors_from_path(distributors_root)
        try:
            cls, cfg = self.loader.get_distributor_by_name('testdistributor')
        except Exception, e:
            print 'plugins: ',
            pprint(self.loader._PluginLoader__distributors.plugins)
            print 'configs: ',
            pprint(self.loader._PluginLoader__distributors.configs)
            print 'types: ',
            pprint(self.loader._PluginLoader__distributors.types)
            self.fail('\n'.join((repr(e), traceback.format_exc())))