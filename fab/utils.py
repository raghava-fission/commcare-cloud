import datetime
import os
import pickle
import sys
import traceback
from fabric.operations import sudo
import yaml
import re
from getpass import getpass

from github3 import login
from fabric.api import execute, env
from fabric.colors import magenta

from const import (
    PROJECT_ROOT,
    CACHED_DEPLOY_CHECKPOINT_FILENAME,
    CACHED_DEPLOY_ENV_FILENAME,
    DATE_FMT,
)


global_github = None


def execute_with_timing(fn, *args, **kwargs):
    start_time = datetime.datetime.utcnow()
    execute(fn, *args, **kwargs)
    if env.timing_log:
        with open(env.timing_log, 'a') as timing_log:
            duration = datetime.datetime.utcnow() - start_time
            timing_log.write('{}: {}\n'.format(fn.__name__, duration.seconds))


def get_pillow_env_config(environment):
    pillow_conf = {}
    pillow_file = os.path.join(PROJECT_ROOT, 'pillows', '{}.yml'.format(environment))
    if os.path.exists(pillow_file):
        with open(pillow_file, 'r+') as f:
            yml = yaml.load(f)
            pillow_conf.update(yml)
    else:
        return None

    return pillow_conf


class DeployMetadata(object):
    def __init__(self, code_branch, environment):
        self.timestamp = datetime.datetime.utcnow().strftime(DATE_FMT)
        self._deploy_ref = None
        self._deploy_tag = None
        self._max_tags = 100
        self._last_tag = None
        self._code_branch = code_branch
        self._environment = environment

    def tag_commit(self):
        pattern = ".*-{}-.*".format(re.escape(self._environment))
        github = _get_github()
        repo = github.repository('dimagi', 'commcare-hq')
        for tag in repo.tags(self._max_tags):
            if re.match(pattern, tag.name):
                self._last_tag = tag.name
                break

        if not self._last_tag:
            print magenta('Warning: No previous tag found in last {} tags for {}'.format(
                self._max_tags,
                self._environment
            ))
        tag_name = "{}-{}-deploy".format(self.timestamp, self._environment)
        msg = "{} deploy at {}".format(self._environment, self.timestamp)
        user = github.me()
        repo.create_tag(
            tag=tag_name,
            message=msg,
            sha=self.deploy_ref,
            obj_type='commit',
            tagger={
                'name': user.login,
                'email': user.email or '{}@dimagi.com'.format(user.login),
                'date': datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'),
            }
        )
        self._deploy_tag = tag_name

    @property
    def diff_url(self):
        if self._deploy_tag is None:
            raise Exception("You haven't tagged anything yet.")
        return "https://github.com/dimagi/commcare-hq/compare/{}...{}".format(
            self._last_tag,
            self._deploy_tag,
        )

    @property
    def deploy_ref(self):
        github = _get_github()
        repo = github.repository('dimagi', 'commcare-hq')
        if self._deploy_ref is None:
            # turn whatever `code_branch` is into a commit hash
            branch = repo.branch(self._code_branch)
            self._deploy_ref = branch.commit.sha
        return self._deploy_ref


def _get_github():
    """
    This grabs the dimagi github account and stores the state in a global variable.
    We do not store it in `env` or `DeployMetadata` so that it's possible to
    unpickle the `env` object without hitting the recursion limit.
    """
    global global_github

    if global_github is not None:
        return global_github
    try:
        from .config import GITHUB_APIKEY
    except ImportError:
        print (
            "You can add a GitHub API key to automate this step:\n"
            "    $ cp {project_root}/config.example.py {project_root}/config.py\n"
            "Then edit {project_root}/config.py"
        ).format(project_root=PROJECT_ROOT)
        username = raw_input('Github username: ')
        password = getpass('Github password: ')
        global_github = login(
            username=username,
            password=password,
        )
    else:
        global_github = login(
            token=GITHUB_APIKEY,
        )

    return global_github


def _get_checkpoint_filename():
    return '{}_{}'.format(env.environment, CACHED_DEPLOY_CHECKPOINT_FILENAME)


def _get_env_filename():
    return '{}_{}'.format(env.environment, CACHED_DEPLOY_ENV_FILENAME)


def cache_deploy_state(command_index):
    with open(os.path.join(PROJECT_ROOT, _get_checkpoint_filename()), 'w') as f:
        pickle.dump(command_index, f)
    with open(os.path.join(PROJECT_ROOT, _get_env_filename()), 'w') as f:
        pickle.dump(env, f)


def clear_cached_deploy():
    os.remove(os.path.join(PROJECT_ROOT, _get_checkpoint_filename()))
    os.remove(os.path.join(PROJECT_ROOT, _get_env_filename()))


def retrieve_cached_deploy_env():
    filename = os.path.join(PROJECT_ROOT, _get_env_filename())
    return _retrieve_cached(filename)


def retrieve_cached_deploy_checkpoint():
    filename = os.path.join(PROJECT_ROOT, _get_checkpoint_filename())
    return _retrieve_cached(filename)


def _retrieve_cached(filename):
    with open(filename, 'r') as f:
        return pickle.load(f)


def traceback_string():
    exc_type, exc, tb = sys.exc_info()
    trace = "".join(traceback.format_tb(tb))
    return u"Traceback:\n{trace}{type}: {exc}".format(
        trace=trace,
        type=exc_type.__name__,
        exc=exc,
    ).replace('"', '\\"')


def pip_install(cmd_prefix, requirements, timeout=None, quiet=False, proxy=None):
    parts = [cmd_prefix, 'pip install']
    if timeout is not None:
        parts.append('--timeout {}'.format(timeout))
    if quiet:
        parts.append('--quiet')
    for requirement in requirements:
        parts.append('--requirement {}'.format(requirement))
    if proxy is not None:
        parts.append('--proxy {}'.format(proxy))
    sudo(' '.join(parts))

def bower_command(command, production=True, config=None):
    parts = ['bower', command]
    if production:
        parts.append('--production')
    if config:
        for key, value in config.items():
            parts.append('--config.{}={}'.format(key,value))
    sudo(' '.join(parts))
