import sys
from types import ModuleType

# Minimal nose stub
nose = ModuleType('nose')
class SkipTest(Exception):
    pass
nose.SkipTest = SkipTest

# nose.tools
nose_tools = ModuleType('nose.tools')

def raises(*exc_types):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                func(*args, **kwargs)
            except exc_types:
                return
            raise AssertionError('Did not raise')
        return wrapper
    return decorator

def ok_(expr, msg=None):
    if not expr:
        raise AssertionError(msg or 'expression is not true')

def eq_(a, b, msg=None):
    if a != b:
        raise AssertionError(msg or f'{a!r} != {b!r}')

nose_tools.raises = raises
nose_tools.ok_ = ok_
nose_tools.eq_ = eq_

# nose.plugins.attrib
nose_plugins = ModuleType('nose.plugins')
nose_attrib = ModuleType('nose.plugins.attrib')

def attr(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

nose_attrib.attr = attr
nose_plugins.attrib = nose_attrib

# register modules
sys.modules.setdefault('nose', nose)
sys.modules.setdefault('nose.tools', nose_tools)
sys.modules.setdefault('nose.plugins', nose_plugins)
sys.modules.setdefault('nose.plugins.attrib', nose_attrib)

# Minimal apt stub
apt = ModuleType('apt')
apt_cache = ModuleType('apt.cache')

class Cache(dict):
    def open(self):
        pass

apt_cache.Cache = Cache
apt.cache = apt_cache

sys.modules.setdefault('apt', apt)
sys.modules.setdefault('apt.cache', apt_cache)
