from typing import Dict
from dakv.codec.base import BaseCodec
from dakv.codec.fp16_raw import FP16RawCodec
from dakv.codec.int8_symm import Int8SymmetricCodec


_CODEC_REGISTRY: Dict[str, BaseCodec] = {}


def register_codec(codec: BaseCodec):
    _CODEC_REGISTRY[codec.name] = codec


def get_codec(name: str) -> BaseCodec:
    if name not in _CODEC_REGISTRY:
        raise ValueError(f"Unknown codec: {name}")
    return _CODEC_REGISTRY[name]


def init_default_codecs():
    register_codec(FP16RawCodec())
    register_codec(Int8SymmetricCodec())


init_default_codecs()
