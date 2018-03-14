import os
import re

import yaml


def load_cluster(path):
    with open(path, "r") as f:
        raw = f.read()
        # Replace env variables in the yaml defs.
        for match, env_var in re.findall(r"(%\(([A-Za-z_]+)\))", raw):
            raw = raw.replace(match, os.environ[env_var])
    data = yaml.load(raw)
    return data
