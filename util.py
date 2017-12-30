#!/usr/bin/env python3

import subprocess
import pickle

from .object_model import *

def isLoc(loc):
    try:
        ext = loc.split('.')[1]
        return True
    except:
        return False

def isJarvisClass(obj):
    return type(obj) == Artifact or type(obj) == Action or type(obj) == Literal

def isPickle(loc):
    try:
        return loc.split('.')[1] == 'pkl'
    except:
        return False

def isCsv(loc):
    try:
        return loc.split('.')[1] == 'csv'
    except:
        return False

def isIpynb(loc):
    return loc.split('.')[1] == 'ipynb'

def isIterable(obj):
    return type(obj) == list or type(obj) == tuple

def runProc(bashCommand):
    process = subprocess.Popen(bashCommand.split(), stdout=subprocess.PIPE)
    output, error = process.communicate()
    return str(output, 'UTF-8')

def pickleTo(obj, loc):
    with open(loc, 'wb') as f:
        pickle.dump(obj, f)

def unpickle(loc):
    with open(loc, 'rb') as f:
        x = pickle.load(f)
    return x

def isOrphan(obj):
    return type(obj) == Literal or (type(obj) == Artifact and obj.parent is None)

def isNumber(s):
    if type(s) == int or type(s) == float:
        return True
    try:
        float(s)
        return True
    except:
        return False

def loadArtifact(loc):
    if isPickle(loc):
        x = unpickle(loc)
    elif isLoc(loc):
        with open(loc, 'r') as f:
            x = [i.strip() for i in f.readlines() if i.strip()]
        if len(x) == 1:
            x = x[0]
    else:
        raise NotImplementedError("Don't know how to load that file.")
    return x

def master_pop(literals):
    if not literals:
        return True
    subtreeMaxed = master_pop(literals[0:-1])
    if subtreeMaxed:
        popSuccess = literals[-1].__pop__()
        if not popSuccess:
            return True
        [literal.__reset__() for literal in literals[0:-1]]
    return False

def activate(pseudoArtifact):
    if type(pseudoArtifact) == Literal:
        pseudoArtifact.__enable__()
    elif not isOrphan(pseudoArtifact) and pseudoArtifact.parent.in_artifacts:
        for in_art in pseudoArtifact.parent.in_artifacts:
            activate(in_art)