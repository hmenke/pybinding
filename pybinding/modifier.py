import inspect
import numpy as np

from . import _cpp
from .support.inspect import get_call_signature

__all__ = ['site_state', 'site_position', 'onsite_energy', 'hopping_energy']


def _check_modifier_spec(func, keywords):
    """Make sure the arguments are specified correctly"""
    argnames = inspect.signature(func).parameters.keys()
    unexpected = ", ".join([name for name in argnames if name not in keywords])
    if unexpected:
        expected = ", ".join(keywords)
        raise RuntimeError("Unexpected argument(s) in modifier: {unexpected}\n"
                           "Arguments must be any of: {expected}".format(**locals()))


def _check_modifier_return(modifier, keywords: list, num_return: int, maybe_complex: bool):
    """Make sure the modifier return the correct type and size"""
    in_shape = 10,
    in_data = np.random.rand(*in_shape).astype(np.float16)

    try:
        out_data = modifier.apply(*(in_data,) * len(keywords))
    except AttributeError as e:
        if "astype" in str(e):  # known issue
            raise RuntimeError("Modifier must return numpy.ndarray")
        else:  # unknown issue
            raise

    out_data = out_data if isinstance(out_data, tuple) else (out_data,)
    if len(out_data) != num_return:
        raise RuntimeError("Modifier expected to return {} ndarray(s), "
                           "but got {}".format(num_return, len(out_data)))
    if any(v.shape != in_shape for v in out_data):
        raise RuntimeError("Modifier must return the same shape ndarray as the arguments")

    if not maybe_complex and modifier.is_complex():
        raise RuntimeError("This modifier must not return complex values")


def _make_modifier(func, base_modifier, keywords: str, num_return=1, maybe_complex=False):
    keywords = [word.strip(",") for word in keywords.split()]
    _check_modifier_spec(func, keywords)

    class Modifier(base_modifier):
        argnames = tuple(inspect.signature(func).parameters.keys())
        try:
            callsig = get_call_signature(up=3)
        except IndexError:
            callsig = get_call_signature(up=0)
            callsig.function = func

        def __str__(self):
            return str(self.callsig)

        def __repr__(self):
            return repr(self.callsig)

        def __call__(self, *args, **kwargs):
            return func(*args, **kwargs)

        def apply(self, *args):
            # only pass the requested arguments to func
            named_args = {name: value for name, value in zip(keywords, args)
                          if name in self.argnames}
            ret = func(**named_args)

            def cast_dtype(v):
                return v.astype(args[0].dtype, casting='same_kind', copy=False)

            try:  # cast output array to same element type as the input
                if isinstance(ret, tuple):
                    return tuple(map(cast_dtype, ret))
                else:
                    return cast_dtype(ret)
            except TypeError:
                return ret

        def is_complex(self):
            ret = self.apply(np.ones(1), *(np.zeros(1) for _ in keywords[1:]))
            return np.iscomplexobj(ret)

    modifier = Modifier()
    _check_modifier_return(modifier, keywords, num_return, maybe_complex)
    return modifier


def site_state(func):
    return _make_modifier(func, _cpp.SiteStateModifier, keywords="state, x, y, z, sub")


def site_position(func):
    return _make_modifier(func, _cpp.PositionModifier, keywords="x, y, z, sub", num_return=3)


def onsite_energy(func):
    return _make_modifier(func, _cpp.OnsiteModifier, keywords="potential, x, y, z, sub")


def hopping_energy(func):
    return _make_modifier(func, _cpp.HoppingModifier, maybe_complex=True,
                          keywords="hopping, hop_id, x1, y1, z1, x2, y2, z2")
