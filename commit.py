import os
import subprocess

PATH = "/home/paki/work/mipsia_master/art"
EXAMPLE = "git fetch https://android.googlesource.com/platform/art refs/changes/65/171665/3 && git cherry-pick FETCH_HEAD"
ABORT_COMMAND = 'git cherry-pick --abort'
UNDO_COMMAND = 'git reset --hard aosp/master'

def work():
    if try_cherry_pick(EXAMPLE):
        print('OKAY')
    else:
        print('NOT OKAY')


def try_cherry_pick(command):
    """ Try a cherry-pick for a commit. Use the specified command passed from
    the fetcher. If the cherry-pick fails, abort the cherry-pick.
    """
    result = subprocess.call(command, shell=True)
    if result != 0:
        subprocess.call(ABORT_COMMAND, shell=True)
        return False
    else:
        return True


def main():
    # TODO: use contextmanager.
    old_path = os.getcwd()
    try:
        os.chdir(PATH)
        work()
    finally:
        os.chdir(old_path)

if __name__ == '__main__':
    main()