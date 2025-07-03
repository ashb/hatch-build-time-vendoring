import subprocess
import sys


def build_project(*args):
    process = subprocess.run([sys.executable, "-m", "build", *args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if process.returncode:  # no cov
        raise Exception(process.stdout.decode("utf-8"))
