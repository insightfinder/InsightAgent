#!/usr/bin/env python
import base64

def decode(obfuscated):
    """ decode an obfuscated string """
    return base64.b64decode(obfuscated).decode('utf-8')


def obfuscate(to_obfuscate):
    """ obfuscate a string """
    return base64.b64encode(to_obfuscate).encode('utf-8')
