#!/usr/bin/env python3

import os
import git
import json
import itertools
import datetime
import pandas as pd
import sys

from graphviz import Digraph, Source
from shutil import copyfile
from shutil import rmtree
from shutil import copytree
from shutil import move

from .. import util
# from .. import above_ground as ag
from .. import viz
from .recursivesizeof import total_size
import time

import ray

class Artifact:

    def __init__(self, loc, parent, manifest, xp_state):
        self.loc = loc
        self.parent = parent

        if self.parent:
            self.parent.out_artifacts.append(self)

        self.xp_state = xp_state

    def __commit__(self):
         pass

    def __getLiteralsAttached__(self):
        # Reset visited for getLiteralsAttached graph traversal
        self.xp_state.visited = []
        literalsAttachedNames = []
        if not self.parent:
            return literalsAttachedNames
        self.parent.__getLiteralsAttached__(literalsAttachedNames)
        return literalsAttachedNames


    def __pull__(self):
        """
        Partially refactored
        :return:
        """
        self.xp_state.visited = []
        driverfile = self.xp_state.jarvisFile

        self.literalNamesAddendum = {}
        if not util.isOrphan(self):
            self.loclist = list(map(lambda x: x.getLocation(), self.parent.out_artifacts))
        else:
            self.loclist = [self.getLocation(),]
        self.scriptNames = []
        if not util.isOrphan(self):
            self.parent.__run__(self.loclist, self.scriptNames, self.literalNamesAddendum)
        
        self.loclist = list(set(self.loclist))
        self.scriptNames = list(set(self.scriptNames))


        # Need to sort to compare
        self.loclist.sort()
        self.scriptNames.sort()

    def parallelPull(self, manifest={}):
        try:
            ray.get([])
        except:
            ray.init()

        self.xp_state.versioningDirectory = os.path.expanduser('~') + '/' + 'jarvis.d'

        tmpexperiment = self.xp_state.tmpexperiment
        if os.path.exists(tmpexperiment):
            rmtree(tmpexperiment)
        os.mkdir(tmpexperiment)

        self.xp_state.visited = []

        if not util.isOrphan(self):
            self.loclist = list(map(lambda x: x.getLocation(), self.parent.out_artifacts))
        else:
            self.loclist = [self.getLocation(), ]
        self.scriptNames = []

        literalsAttached = set([])
        lambdas = []

        if not util.isOrphan(self):
            self.parent.__serialize__(lambdas, self.loclist, self.scriptNames)

        self.loclist = list(set(self.loclist))
        self.scriptNames = list(set(self.scriptNames)) 

        self.loclist.sort()
        self.scriptNames.sort()  

        for _, names in lambdas:
            literalsAttached |= set(names)

        original_dir = os.getcwd()
        experimentName = self.xp_state.EXPERIMENT_NAME
        numTrials = 1
        literals = []
        literalNames = []
        config = {}

        for kee in self.xp_state.literalNameToObj:
            if kee in literalsAttached:
                config[kee] = self.xp_state.literalNameToObj[kee].v
                if self.xp_state.literalNameToObj[kee].__oneByOne__:
                    numTrials *= len(self.xp_state.literalNameToObj[kee].v)
                    literals.append(self.xp_state.literalNameToObj[kee].v)
                else:
                    if type(self.xp_state.literalNameToObj[kee].v) == tuple:
                        literals.append((self.xp_state.literalNameToObj[kee].v,))
                    else:
                        literals.append([self.xp_state.literalNameToObj[kee].v, ])
                literalNames.append(kee)

        literals = list(itertools.product(*literals))

        for i in range(numTrials):
            dst = tmpexperiment + '/' + str(i)
            copytree(os.getcwd(), dst, True)  

        ts = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')  
        self.xp_state.ray['literalNames'] = literalNames  

        config['6zax7937'] = literals
        config['8ilk9274'] = literalNames
        
        @ray.remote
        def helperChangeDir(dir_path, lambdas, literals, config):
            os.chdir(dir_path)
            i = 0
            for f, names in lambdas:
                for each in names:
                    if i < len(literals):
                        config[each] = literals[i]
                        i += 1
                literal = list(map(lambda x: config[x], names))
                f(literal) 

            with open('.' + experimentName + '.jarvis', 'w') as fp:
                json.dump(config, fp)

        remaining_ids = []

        for i in range(numTrials):
            dir_path = tmpexperiment + '/' + str(i)
            remaining_ids.append(helperChangeDir.remote(dir_path, lambdas, literals[i], config))

        _, _ = ray.wait(remaining_ids, num_returns=numTrials)

        if not os.path.isdir(self.xp_state.versioningDirectory):
            os.mkdir(self.xp_state.versioningDirectory)

        moveBackFlag = False

        if os.path.exists(self.xp_state.versioningDirectory + '/' + self.xp_state.EXPERIMENT_NAME):
            move(self.xp_state.versioningDirectory + '/' + self.xp_state.EXPERIMENT_NAME + '/.git', '/tmp/')
            rmtree(self.xp_state.versioningDirectory + '/' + self.xp_state.EXPERIMENT_NAME)
            moveBackFlag = True

        if manifest:
            os.chdir(tmpexperiment)

            dirs = [x for x in os.listdir() if util.isNumber(x)]
            dirs.sort()
            table_full = []
            table_small = []

            for trial in dirs:
                os.chdir(trial)
                with open('.' + experimentName + '.jarvis', 'r') as fp: #error here
                    config = json.load(fp)
                record_full = {}
                record_small = {}

                for literalName in literalNames:
                    record_full[literalName] = config[literalName]
                    record_small[literalName] = config[literalName]

                for artifactLabel in manifest:
                    record_full[artifactLabel] = util.loadArtifact(manifest[artifactLabel].loc)
                    if total_size(record_full[artifactLabel]) >= 1000:
                        record_small[artifactLabel] = " . . . "
                    else:
                        record_small[artifactLabel] = record_full[artifactLabel]
                    if util.isNumber(record_full[artifactLabel]):
                        record_full[artifactLabel] = eval(record_full[artifactLabel])
                    if util.isNumber(record_small[artifactLabel]):
                        record_small[artifactLabel] = eval(record_small[artifactLabel])
                record_small['__trialNum__'] = trial
                record_full['__trialNum__'] = trial

                table_full.append(record_full)
                table_small.append(record_small)
                os.chdir('../')

            df = pd.DataFrame(table_small)
            util.pickleTo(df, experimentName + '.pkl')

            os.chdir(original_dir)

        copytree(tmpexperiment, self.xp_state.versioningDirectory + '/' + self.xp_state.EXPERIMENT_NAME)

        os.chdir(self.xp_state.versioningDirectory + '/' + self.xp_state.EXPERIMENT_NAME)
        if moveBackFlag:
            move('/tmp/.git', self.xp_state.versioningDirectory + '/' + self.xp_state.EXPERIMENT_NAME)
            repo = git.Repo(os.getcwd())
            repo.git.add(A=True)
            repo.index.commit('incremental commit')
        else:
            repo = git.Repo.init(os.getcwd())
            repo.git.add(A=True)
            repo.index.commit('initial commit')
        os.chdir(original_dir)

        self.__commit__()

        if manifest:
            return pd.DataFrame(table_full)


    def pull(self, manifest={}):

        self.xp_state.versioningDirectory = os.path.expanduser('~') + '/' + 'jarvis.d'

        # Recreate the tmpexperiment directory
        tmpexperiment = self.xp_state.tmpexperiment
        if os.path.exists(tmpexperiment):
            rmtree(tmpexperiment)
            os.mkdir(tmpexperiment)
        else:
            os.mkdir(tmpexperiment)

        self.xp_state.visited = []
        util.activate(self)
        userDefFiles = set(os.listdir()) - self.xp_state.ghostFiles
        experimentName = self.xp_state.EXPERIMENT_NAME
        try:
            currTrialNum = 0
            while True:
                # Pull all literals and create trial directories.
                self.__pull__()

                # Write the config file
                config = {}
                for litName in self.literalNamesAddendum:
                    config[litName] = util.unpickle(self.literalNamesAddendum[litName])
                with open('.' + experimentName + '.jarvis', 'w') as fp:
                    json.dump(config, fp)

                dst = tmpexperiment + '/' + str(currTrialNum)
                copytree(os.getcwd(), dst, True)
                subtreeMaxed = util.master_pop(self.xp_state.literals)
                if subtreeMaxed:
                    break
                currTrialNum += 1
        except Exception as e:
            try:
                intermediateFiles = set(self.loclist) - userDefFiles
                for file in intermediateFiles:
                    if os.path.exists(file):
                        os.remove(file)
            except Exception as ee:
                print(ee)
            self.xp_state.literals = []
            self.xp_state.ghostFiles = set([])
            raise e

        intermediateFiles = set(self.loclist) - userDefFiles
        for file in intermediateFiles:
            os.remove(file)
        os.remove('.' + experimentName + '.jarvis')
        original_dir = os.getcwd()

        # Create versioning directory jarvis.d
        if not os.path.isdir(self.xp_state.versioningDirectory):
            os.mkdir(self.xp_state.versioningDirectory)

        # Copy all relevant files into the versioning directory.
        # for file in (userDefFiles & (set(self.loclist) | set(self.scriptNames))):
        #     copyfile(file, self.xp_state.versioningDirectory + '/' + file)

        os.chdir(self.xp_state.versioningDirectory)

        self.xp_state.literals = []
        self.xp_state.ghostFiles = set([])

        moveBackFlag = False

        # move back  .git file in the versioning directory to the /tmp folder. Delete experiment folder in versioning directory.
        if os.path.exists(self.xp_state.versioningDirectory + '/' + experimentName):
            move(self.xp_state.versioningDirectory + '/' + experimentName + '/.git', '/tmp/')
            rmtree(self.xp_state.versioningDirectory + '/' + experimentName)
            moveBackFlag = True

        if manifest:
            os.chdir(tmpexperiment)

            dirs = [x for x in os.listdir() if util.isNumber(x)]
            dirs.sort()
            table_full = []
            table_small = []

            for trial in dirs:
                os.chdir(trial)
                with open('.' + experimentName + '.jarvis', 'r') as fp: #error here
                    config = json.load(fp)
                record_full = {}
                record_small = {}

                for literalName in self.literalNamesAddendum:
                    record_full[literalName] = config[literalName]
                    record_small[literalName] = config[literalName]

                for artifactLabel in manifest:
                    record_full[artifactLabel] = util.loadArtifact(manifest[artifactLabel].loc)
                    if total_size(record_full[artifactLabel]) >= 1000:
                        record_small[artifactLabel] = " . . . "
                    else:
                        record_small[artifactLabel] = record_full[artifactLabel]
                    if util.isNumber(record_full[artifactLabel]):
                        record_full[artifactLabel] = eval(record_full[artifactLabel])
                    if util.isNumber(record_small[artifactLabel]):
                        record_small[artifactLabel] = eval(record_small[artifactLabel])
                record_small['__trialNum__'] = trial
                record_full['__trialNum__'] = trial

                table_full.append(record_full)
                table_small.append(record_small)
                os.chdir('../')

            df = pd.DataFrame(table_small)
            util.pickleTo(df, experimentName + '.pkl')

            os.chdir(original_dir)

        # Copy the tmpexperiment directory to the versioning jarvis.d directory and change to that directory.
        copytree(tmpexperiment, self.xp_state.versioningDirectory + '/' + experimentName)
        os.chdir(self.xp_state.versioningDirectory + '/' + experimentName)

        if moveBackFlag:
            move('/tmp/.git', self.xp_state.versioningDirectory + '/' + self.xp_state.EXPERIMENT_NAME)
            repo = git.Repo(os.getcwd())
            repo.git.add(A=True)
            repo.index.commit('incremental commit')
        else:
            repo = git.Repo.init(os.getcwd())
            repo.git.add(A=True)
            repo.index.commit('initial commit')
        os.chdir(original_dir)

        self.__commit__()

    def peek(self, head=25, taip='default', func = lambda x: x):
        trueVersioningDir = self.xp_state.versioningDirectory
        self.xp_state.versioningDirectory = os.path.expanduser('~') + '/' + '1fdf8583bfd663e98918dea393e273cc'

        # Create temporary versioning directory to store files
        if os.path.exists(self.xp_state.versioningDirectory):
            rmtree(self.xp_state.versioningDirectory)
            os.mkdir(self.xp_state.versioningDirectory)
        else:
            os.mkdir(self.xp_state.versioningDirectory)

        # Update elements visited and literals array
        self.xp_state.visited = []
        util.activate(self)

        if taip == "default":
            try:
                # Just pull once and put output in folder peek0 within versioning directory.
                original_dir = os.getcwd()
                dst = self.xp_state.versioningDirectory + '/' + "peek0"
                copytree(os.getcwd(), dst, True)
                os.chdir(dst)
                self.__pull__()

                # dst = self.xp_state.versioningDirectory + '/' + "peek0"
                # copytree(os.getcwd(), dst, True)

                # Unpickle and read the file to output.
                if util.isPickle(dst + "/" + self.loc):
                    out = func(util.unpickle(dst + '/' + self.loc))
                else:
                    out = []
                    with open(dst + '/' + self.loc, 'r') as f:
                        for i in range(head):
                            out.append(f.readline())
                    out = func(out)

                os.chdir(original_dir)
                # [os.remove(i) for i in self.xp_state.ghostFiles] # We want to keep resources intact
            except Exception as e:
                print(e)
                out = e
        # TODO: add case for peek next.

        # Delete the temporary versioning directory created.
        try:
            rmtree(self.xp_state.versioningDirectory)
        except:
            pass
        # Reset versioning directory to original jarvis.d directory.
        self.xp_state.versioningDirectory = trueVersioningDir
        return out


    def plot(self, rankdir=None):
        # Prep globals, passed through arguments

        self.xp_state.nodes = {}
        self.xp_state.edges = []

        dot = Digraph()
        # diagram = {"dot": dot, "counter": 0, "sha": {}}

        if not util.isOrphan(self):
            # self.parent.__plotWalk__(diagram)
            vg = viz.VizGraph()
            self.parent.__plotWalk__(vg)
            # vg.bft()
            vg.to_graphViz()
            Source.from_file('output.gv').view()
        else:
            node_diagram_id = '0'
            dot.node(node_diagram_id, self.loc, shape="box")
            self.xp_state.nodes[self.loc] = node_diagram_id
            dot.format = 'png'
            if rankdir == 'LR':
                dot.attr(rankdir='LR')
            dot.render('driver.gv', view=True)



    def getLocation(self):
        return self.loc