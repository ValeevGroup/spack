##############################################################################
# Copyright (c) 2013-2018, Lawrence Livermore National Security, LLC.
# Produced at the Lawrence Livermore National Laboratory.
#
# This file is part of Spack.
# Created by Todd Gamblin, tgamblin@llnl.gov, All rights reserved.
# LLNL-CODE-647188
#
# For details, see https://github.com/spack/spack
# Please also see the NOTICE and LICENSE files for our notice and the LGPL.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License (as
# published by the Free Software Foundation) version 2.1, February 1999.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the IMPLIED WARRANTY OF
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the terms and
# conditions of the GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
##############################################################################
"""
This module contains routines related to the module command for accessing and
parsing environment modules.
"""
import subprocess
import os
import json


# This list is not exhaustive. Currently we only use load and unload
# If we need another option that changes the environment, add it here.
module_change_commands = ['load', 'swap', 'unload', 'purge', 'use', 'unuse']
py_cmd = "$'import os\nimport json\nprint(json.dumps(dict(os.environ)))'"


def module(*args):
    if args[0] in module_change_commands:
        # Do the module manipulation, then output the environment in JSON
        # and read the JSON back in the parent process to update os.environ
        module_p  = subprocess.Popen('module ' + ' '.join(args) + ' 2>&1' + 
                                     ' >/dev/null; python -c %s' % py_cmd,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, shell=True)

        # Cray modules spit out warnings that we cannot supress.
        # This hack skips to the last output (the environment)
        env_output =  module_p.communicate()[0]
        env = env_output.strip().split('\n')[-1]

        # Update os.environ with new dict
        env_dict = json.loads(env)
        os.environ.clear()
        os.environ.update(env_dict)
    else:
        # Simply execute commands that don't change state and return output
        module_p = subprocess.Popen('module ' + ' '.join(args) + ' 2>&1',
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, shell=True)
        # Decode and str to return a string object in both python 2 and 3
        return str(module_p.communicate()[0].decode())


def load_module(mod):
    """Takes a module name and removes modules until it is possible to
    load that module. It then loads the provided module. Depends on the
    modulecmd implementation of modules used in cray and lmod.
    """
    # Read the module and remove any conflicting modules
    # We do this without checking that they are already installed
    # for ease of programming because unloading a module that is not
    # loaded does nothing.
    text = module('show', mod).split()
    for i, word in enumerate(text):
        if word == 'conflict':
            module('unload', text[i + 1])

    # Load the module now that there are no conflicts
    # Some module systems use stdout and some use stderr
    module('load', mod)


def get_argument_from_module_line(line):
    if '(' in line and ')' in line:
        # Determine which lua quote symbol is being used for the argument
        comma_index = line.index(',')
        cline = line[comma_index:]
        try:
            quote_index = min(cline.find(q) for q in ['"', "'"] if q in cline)
            lua_quote = cline[quote_index]
        except ValueError:
            # Change error text to describe what is going on.
            raise ValueError("No lua quote symbol found in lmod module line.")
        words_and_symbols = line.split(lua_quote)
        return words_and_symbols[-2]
    else:
        return line.split()[2]


def get_path_from_module(mod):
    """Inspects a TCL module for entries that indicate the absolute path
    at which the library supported by said module can be found.
    """
    # Read the module
    text = module('show', mod).split('\n')

    # If it sets the LD_LIBRARY_PATH or CRAY_LD_LIBRARY_PATH, use that
    for line in text:
        if line.find('LD_LIBRARY_PATH') >= 0:
            path = get_argument_from_module_line(line)
            return path[:path.find('/lib')]

    # If it lists its package directory, return that
    for line in text:
        if line.find(mod.upper() + '_DIR') >= 0:
            return get_argument_from_module_line(line)

    # If it lists a -rpath instruction, use that
    for line in text:
        rpath = line.find('-rpath/')
        if rpath >= 0:
            return line[rpath + 6:line.find('/lib')]

    # If it lists a -L instruction, use that
    for line in text:
        L = line.find('-L/')
        if L >= 0:
            return line[L + 2:line.find('/lib')]

    # If it sets the PATH, use it
    for line in text:
        if line.find('PATH') >= 0:
            path = get_argument_from_module_line(line)
            return path[:path.find('/bin')]

    # Unable to find module path
    return None
