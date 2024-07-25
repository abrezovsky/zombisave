import argparse
import importlib.util
import os
import pathlib
import shutil
import sys
import time
import zipfile as zip

# TODO: Argparse (playstyle override?, extension?), readme.md, use logging?
# Does not verify saves, ALL folders in save directory other than FOLDER_NAME are backup candidates 
# Only catching exceptions the first time a type of os operation is attempted, shouldn't be an issue

SAVE_DIR_DEFAULT = pathlib.Path("~","Zomboid","Saves")
FOLDER_DEFAULT = "save_backups"
LEVEL_DEFAULT = 5
INTERVAL_DEFAULT = 30
SAVE_LIMIT_DEFAULT = 0

# Argument parsing setup
DESCRIPTION = "Script to automatically back up Project Zomboid saves"

compression_choices = ["NONE", "STORED"]
compression_default = "STORED"
# Determine which compression methods are available
if importlib.util.find_spec("zlib"):
    compression_choices.append("DEFLATED")
    compression_default = "DEFLATED"
if importlib.util.find_spec("bz2"):
    compression_choices.append("BZIP2")
if importlib.util.find_spec("lzma"):
    compression_choices.append("LZMA")
METHODS = {"NONE": None, "STORED": zip.ZIP_STORED, "DEFLATED": zip.ZIP_DEFLATED, "BZIP2": zip.ZIP_BZIP2, "LZMA": zip.ZIP_LZMA}

SAVE_DIR_HELP = f"Save directory location, use if it has been changed from the default of \"{SAVE_DIR_DEFAULT}\""
FOLDER_HELP = f"Name of the backup folder, default is \"{FOLDER_DEFAULT}\", use \".\" to create backups inside the save directory"
COMPRESSION_HELP = "Compression method, choices and default depend on system availability, \"NONE\" just copies the save folder"
LEVEL_HELP = f"Compression level, only applies to DEFLATED (0-9) and BZIP2 (1-9) methods, lower is faster with less compression, defaults to {LEVEL_DEFAULT}"
INTERVAL_HELP = f"Backup interval in minutes, defaults to {INTERVAL_DEFAULT} minutes"
SAVE_LIMIT_HELP = f"Limit number of backups per save, default (0) is unlimited"

parser = argparse.ArgumentParser(description=DESCRIPTION)
parser.add_argument("-d", "--directory", metavar="DIR", default=SAVE_DIR_DEFAULT, help=SAVE_DIR_HELP)
parser.add_argument("-f", "--folder", metavar="NAME", default=FOLDER_DEFAULT, help=FOLDER_HELP)
parser.add_argument("-c", "--compression", metavar="METHOD", type=str.upper, choices=compression_choices, default=compression_default, help=COMPRESSION_HELP)
parser.add_argument("-l", "--level", metavar="#", type=int, default=LEVEL_DEFAULT, help=LEVEL_HELP)
parser.add_argument("-i", "--interval", metavar="#", type=int, default=INTERVAL_DEFAULT, help=INTERVAL_HELP)
parser.add_argument("-n", "--number", metavar="#", type=int, default=SAVE_LIMIT_DEFAULT, help=SAVE_LIMIT_HELP)
args = parser.parse_args()

# Transform folder special case
if args.folder == ".":
    args.folder = ""
    # NOTE: If extension option is added to arguments, set it to "" here

# Sanitize compression level
if (args.compression == "DEFLATED" and (args.level not in range(10))) or (args.compression == "BZIP2" and (args.level not in range(1, 10))):
    print(f"WARNING: Invalid compression level, reverting to default of {LEVEL_DEFAULT}")
    args.level = LEVEL_DEFAULT

#Sanitize save limit
if args.number < 0:
    print(f"ERROR: Backup limit value must be a positive integer!")
    sys.exit(1)

# Script constants
FOLDER_NAME = args.folder            # Backup folder name  
METHOD = METHODS[args.compression]   # Backup compression method
LEVEL = args.level                   # Backup compression level (valid values depend on METHOD)
INTERVAL = args.interval             # Backup interval (in minutes)
LIMIT = args.number                  # Backup limit

# Get the absolute path to saves directory
SAVE_ROOT_DIR = os.path.expanduser(args.directory)

# Choose the save to back up
# List all playstyle directories
try:
    playstyles = os.listdir(SAVE_ROOT_DIR)
except PermissionError:
    print("ERROR: Do not have permissions to access save directory!")
    sys.exit(1)

# Error out if there are no folders
if playstyles == []:
    print("ERROR: No saves found!")
    sys.exit(1)

# Find the latest save, by modification time, for all playstyles
latest_playstyle = playstyles[0]
latest_save = ""
latest_modified = 0.0

for playstyle in playstyles:
    for save in os.listdir(pathlib.Path(SAVE_ROOT_DIR, playstyle)):
        # Ignore our backup folder
        if save == FOLDER_NAME:
            continue

        modified_time = os.path.getmtime(pathlib.Path(SAVE_ROOT_DIR, playstyle, save))
        if modified_time > latest_modified:
            latest_playstyle = playstyle
            latest_save = save
            latest_modified = modified_time

# Error out if we didn't find any saves
if latest_save == "":
    print("ERROR: No saves found!")
    sys.exit(1)

SAVE_DIR = pathlib.Path(SAVE_ROOT_DIR, latest_playstyle)

# Create the backup directory, if it doesn't already exist
BACKUP_PATH = pathlib.Path(SAVE_DIR, FOLDER_NAME)
try:
    os.mkdir(BACKUP_PATH)
except FileExistsError:
    pass
except PermissionError:
    print("ERROR: Do not have permissions to create backup directory!")
    sys.exit(1)

# Set default backup suffix
SUFFIX_SEPARATOR = '_'     # Backup file name separator from addon
SUFFIX_BEGIN = "bak"      # Backup file name addon prefix
suffix_extension = ".zip"  # Backup file name addon extension
backup_num = 0             # Current backup number

# Set initial backup number, also set current number of backups (for LIMIT, if applicable)
total_num = 0         # Total number of backups

for backup in os.listdir(BACKUP_PATH):
    if latest_save in backup:
        total_num += 1

        # Determine existing backup's number, set initial backup number to one higher if it is <= the current initial
        before, sep, after = backup.rpartition(SUFFIX_SEPARATOR)
        after = after.removeprefix(SUFFIX_BEGIN).removesuffix(suffix_extension)
        if int(after) >= backup_num:
            backup_num = int(after) + 1

last_mod = 0     # Modification time of last backup
current_mod = 1  # Modification time of save currently

# Create a new backup until it hasn't been modified during INTERVAL
while current_mod != last_mod:

    # If a save limit exists, delete saves until we are under the limit
    if LIMIT:
        while total_num >= LIMIT:  # This must be a while in case we start  more than 1 above the limit
            earliest_backup = ""
            earliest_mod = 0

            for backup in os.listdir(BACKUP_PATH):
                if latest_save in backup:
                    modified_time = os.path.getmtime(pathlib.Path(BACKUP_PATH, backup))
                    if (not earliest_mod) or (modified_time < earliest_mod):
                        earliest_backup = backup
                        earliest_mod = modified_time

            print(f"Backup limit reached, deleting {earliest_backup}")
            backup_path = pathlib.Path(BACKUP_PATH, earliest_backup)
            try:
                if os.path.isfile(backup_path):
                    os.remove(backup_path)
                else:
                    os.rmdir(backup_path)
            except PermissionError:
                print("ERROR: Do not have permissions to delete backup")

            total_num -= 1
    
    # Add an extension if we are zipping
    if not METHOD:
        suffix_extension = ""

    backup_name = f"{latest_save}{SUFFIX_SEPARATOR}{SUFFIX_BEGIN}{backup_num}{suffix_extension}"

    # If file name already exists, increment the number (should only occur if user deletes files manually)
    while os.path.isfile(pathlib.Path(BACKUP_PATH, backup_name)): 
        backup_num += 1
        backup_name = f"{latest_save}{SUFFIX_SEPARATOR}{SUFFIX_BEGIN}{backup_num}{suffix_extension}"
    
    if FOLDER_NAME == "":
        print(f"Creating backup \"{latest_playstyle}/{backup_name}\" ... ", end='')
    else:
        print(f"Creating backup \"{latest_playstyle}/{FOLDER_NAME}/{backup_name}\" ... ", end='')
    
    # If zipping, Create a zip file, add the save folder to it
    if METHOD:    
        with zip.ZipFile(pathlib.Path(BACKUP_PATH, backup_name), mode='x', compression=METHOD, compresslevel=LEVEL) as backup:

            # Write the entire save directory structure
            for dirpath, dirs, files in os.walk(pathlib.Path(SAVE_DIR, latest_save)):

                # Add the directories first to ensure empty directories are added
                for dir in dirs:
                    dir_path = pathlib.Path(dirpath, dir)
                    rel_path = dir_path.relative_to(SAVE_DIR)
                    try:
                        backup.write(dir_path, arcname=rel_path)
                    except PermissionError:  # Hopefully this write isn't executed when the ZipFile is closed
                        print("ERROR: Do not have permissions to write directory to backup!")
                        backup.close()
                        sys.exit(1)

                # Add files to the already complete directory structure
                for file in files:
                    file_path = pathlib.Path(dirpath, file)
                    rel_path = file_path.relative_to(SAVE_DIR)
                    backup.write(file_path, arcname=rel_path)
    else:
        # Not zipping, simply copy the save folder
        try:
            shutil.copytree(pathlib.Path(SAVE_DIR, latest_save), pathlib.Path(BACKUP_PATH, backup_name))
        except PermissionError:
            print("ERROR: Do not have permissions to copy save directory!")
            sys.exit(1)

    print("DONE")
    total_num +=1
    backup_num += 1
    last_mod = os.path.getmtime(pathlib.Path(SAVE_DIR, latest_save))

    # Sleep INTERVAL minutes until the next backup time
    wake_time = time.localtime(time.time() + (INTERVAL * 60))
    print(f"Sleeping until {wake_time.tm_hour}:{wake_time.tm_min}, Ctrl+C to exit")
    try:
        time.sleep(INTERVAL * 60)
    except KeyboardInterrupt:
        print("Exiting")
        sys.exit()

    # Check if the save after sleeping to see if it has been modified since
    try:
        current_mod = os.path.getmtime(pathlib.Path(SAVE_DIR, latest_save))
    except FileNotFoundError:
        print("ERROR: Save renamed or deleted during sleep!")
        sys.exit(1)

print("Save hasn't been modified since last backup, exiting.")
