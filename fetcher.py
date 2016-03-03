import itertools
import json
import os
import requests
import subprocess


URL_HEADER      =   'https://android-review.googlesource.com'
CHANGES_HEADER  =   URL_HEADER + '/changes/'
PROJECT         =   'platform/art'
BRANCH          =   'master'
AUTHORS         =   ['Goran Jakovljevic',
                    'Alexey Frunze',
                    'Pavle Batuta', 
                    'Douglas Leung',
                    'Chris Larsen',
                    'Duane Sand',
                    'Nikola Veljkovic',
                    'Lazar Trsic',]

GERRIT_MAGIC_JSON_PREFIX = ")]}\'\n"

PATH = '/home/paki/work/mipsia_master/art'
GIT_CHECKOUT_AUTOMERGE_BRANCH = 'git checkout script_automerger'
GIT_ABORT_CHERRY_PICK = 'git cherry-pick --abort'
GIT_FULL_RESET_AOSP = 'git reset --hard aosp/master'

class CherryPickInfo(object):
    """ 
    This class represents all the necessary information needed to cherry pick
    a single commit from AOSP Gerrit.

    """
    def __init__(self, json_response):
        self.json_response  = json_response
        self.created_time   = self.fetch_created_time()
        self.updated_time   = self.fetch_updated_time()
        self.number         = self.fetch_change_number()

    def __fetch_field(self, field_name, nested_response = None):
        """ Fetch a field with field_name from the JSON response. 
        The nested_response argument is used to daisy-chain JSON array access.

        returns:
            Field contents as string.
        raises:
            KeyError if JSON does not contain said field.
        """
        if nested_response is None:
            response = self.json_response
        else:
            response = nested_response
        try:
            return response[field_name]
        except KeyError:
            raise KeyError('no field ' + field_name + ' in JSON response')

    def fetch_change_id(self):
        """ Return change_id from the response.

        returns:
            Decoded change_id from the response.
        raises:
            KeyError if response does not contain change_id.

        """
        return self.__fetch_field('change_id')
    
    def fetch_change_number(self):
        """ Return the internal change number of the gerrit patch.

        returns:
            Gerrit patch number.
        raises:
            KeyError if _number field is not present.
        """
        return self.__fetch_field('_number')

    def fetch_created_time(self):
        """ Return the time the patch-set was created, as string.

        returns:
            Time the patch was created, as string.
        raises:
            KeyError if response does not contain created time.
        """
        return self.__fetch_field('created')

    def fetch_updated_time(self):
        """ Return the last time the patch-set was updated, as string.

        returns:
            Time the patch-set was last updated, as string.
        raises:
            KeyError if response does not contain updated time.
        """
        return self.__fetch_field('updated')

    def fetch_current_revision(self):
        """ Return the number of the current patch revision, as string.

        returns:
            Number of the current patch revision, as string
        raises:
            KeyError if response does not contain current_revision.
        """
        return self.__fetch_field('current_revision')

    def fetch_cherry_pick_string(self):
        """ Build git cherry-pick string from the JSON response.

        returns: 
            String command for git cherry-pick.
        raises:
            KeyError if the JSON could not be parsed.

        """
        cur_rev_id = self.fetch_current_revision()
        all_revs = self.__fetch_field('revisions')
        cur_rev = self.__fetch_field(cur_rev_id, all_revs)
        fetch = self.__fetch_field('fetch', cur_rev)
        http = self.__fetch_field('http', fetch)
        commands = self.__fetch_field('commands', http)
        cherry_pick = self.__fetch_field('Cherry Pick', commands)
        return cherry_pick

    def fetch_fail_url(self):
        """ Return URL to pass to user when the cherry-pick is unsuccessful.
        The URL has format:
            https://android-review.googlesource.com/#/c/<number>.

        returns:
            URL of the appropriate format.
        raises:
            KeyError if JSON could not be parsed.
        """
        FAIL_URL_HEADER = "https://android-review.googlesource.com/#/c/"
        return FAIL_URL_HEADER + str(self.number) + "/"

    created_time = ""
    updated_time = ""
    number = -1

def call_bash_muted(command):
    """Call an external bash command, with supressed output.

    returns:
        True if command succeds, False otherwise.
    """
    bash_ret = subprocess.call(command, shell=True, stdout=subprocess.DEVNULL, 
                               stderr=subprocess.STDOUT)
    if bash_ret == 0:
        return True
    else:
        return False

def make_all_author_patches_query(project, owner, status='status:open'):
    """ Make a query string for fetching all patches on a project that belong
    to author. The default status is open.

    returns:
        Query string containing all 
    """
    ret =   'project:' + project
    ret +=  ' AND ' + status
    ret +=  ' AND owner:\"' + owner + '\"' 
    return ret

def decode_response(response):
    """ Strip off Gerrit's magic token and return the decoded JSON response.

    returns:
        Decoded JSON content as dict.

    raises:
        requests.HTTPError if the response contains a http error status code.
        ValueError if the JSON could not be decoded.

    """
    content = response.text
    try:
        response.raise_for_status()
    except Exception:
        print('ERROR on response to ' + response.url)
        print('server returns: ' + response.text)

    if content.startswith(GERRIT_MAGIC_JSON_PREFIX):
        content = content[len(GERRIT_MAGIC_JSON_PREFIX):]

    return json.loads(content)

def get_author_cherry_picks(project, author):
    """ For an author, fetch all git cherry-pick commands.
    returns:
        List of tuples (git fetch command, fail display url)
    """
    query_string = make_all_author_patches_query(project, author)
    payload = [('q', query_string),
        ('o', 'CURRENT_REVISION'),   # Required for DOWNLOAD_COMMANDS.
        ('o', 'DOWNLOAD_COMMANDS'),  # Contains the git fetch command string.
        ]
    return_list = []
    response = requests.get(CHANGES_HEADER, params=payload)
    for data in decode_response(response):
        info = CherryPickInfo(data)
        cp_string = info.fetch_cherry_pick_string()
        fail_url = info.fetch_fail_url()
        return_list.append((cp_string, fail_url))

    return return_list

def test_print(in_list):
    """ Output all the patch strings for the purpose of testing/manual patch
    forming. The format is:
    -------------------------------------------------
    cherry-picks for all patches

    fail urls for all patches
    -------------------------------------------------
    """
    for elem in in_list:
        print(elem[0])

    print('')

    for elem in in_list:
        print(elem[1])

def try_cherry_pick(command):
    """ Try a cherry-pick for a commit. Use the specified command passed from
    the fetcher. If the cherry-pick fails, abort it.

    returns:
        True if cherry-pick was successfull, False otherwise.
    """
    res = call_bash_muted(command)
    if not res:
        call_bash_muted(GIT_ABORT_CHERRY_PICK)
    return res

def form_patch_list(sort=True):
    """ Form a list of patches belonging to all authors. The will optionally
    be sorted.

    returns:
        A list of patches belonging to all authors
    """
    patch_list = []
    for author in AUTHORS:
        author_result = get_author_cherry_picks(PROJECT, author)
        if author_result:
            patch_list += author_result

    # Sort the list by commit number:
    patch_list.sort(key=lambda number:number[1])
    return patch_list

def try_regular_list(patch_list):
    """ Try and cherry-pick every patch on top of current master, then build
    a list of all patches that can be cherry-picked like this. The patches
    that cannot be cherry-picked in regular order are set aside for manual
    inspection. 

    returns:
        Tuple (A, B):
            A: list of patches merged in regular order
            B: sorted list of patches that cannot be merged in regular order
    """
    # TODO: do this through decorator/contextmanager.
    regular_list = []
    unmerged_list = []
    old_path = os.getcwd()  
    try:
        os.chdir(PATH)
        call_bash_muted(GIT_CHECKOUT_AUTOMERGE_BRANCH)
        # Reset the branch to master before applyting any changes.
        call_bash_muted(GIT_FULL_RESET_AOSP)
        for patch in patch_list:
            if try_cherry_pick(patch[0]):
                regular_list.append(patch)
            else:
                unmerged_list.append(patch)
    finally:
        os.chdir(old_path)
    return (regular_list, unmerged_list)

def print_report(start_list, regular_list, unmerged_list,
                 merge_broken_commands = True):
    """Print a final report of the patch merger. The report has the following
    format:

    Merge report:
    Project: <branch_name>
    Branch: master
    Authors: <name>, <name>, ...

    Open patches:
    https://android-review.googlesource.com/#/c/<num>/
    ...

    The following commands will merge the patches in regular order:
    git fetch https://android.googlesource.com/platform/art
        refs/changes/65/<patch_no>/<ps_no> && git cherry-pick FETCH_HEAD
    ...

    Unable to merge patches:
    https://android-review.googlesource.com/#/c/<num>/
    ...

    You can try and merge conflicting patches with the following commands:
    git fetch https://android.googlesource.com/platform/art
        refs/changes/65/<patch_no>/<ps_no> && git cherry-pick FETCH_HEAD
    ...

    """
    # TODO: figure out a nicer way to print tuples other than for...
    print('Patch list report:')
    print('Project:', PROJECT)
    print('Branch:', BRANCH)
    print('Authors:', *AUTHORS, sep=' ')
    print()
    print('Open patches:')
    for patch_tuple in start_list:
        print(patch_tuple[1])
    print()
    print('The following commands will merge the patches in regular order:')
    for patch_tuple in regular_list:
            print(patch_tuple[0])
    print()
    print('Unable to merge patches:')
    for patch_tuple in unmerged_list:
        print(patch_tuple[1])
    print()
    print('You may try to merge conflicting patches with the following',
          'commands:')
    for patch_tuple in unmerged_list:
        print(patch_tuple[0])
    print()


def main():
    # TODO:
    # Take the list of patches and build all possible combinations.
    # Submit the combinations to mipsia art git.
    # Find the longest combination and prepare a patch list.
    fetched_tuples = form_patch_list()
    (regular_list, unmerged_list) = try_regular_list(fetched_tuples)
    print_report(fetched_tuples, regular_list, unmerged_list)
    # For now, check out master branch and leave everything unchanged.

if __name__ == '__main__':
    main()