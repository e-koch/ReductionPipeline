
import sys
import os
from casatasks import importasdm

from lband_pipeline.ms_split_tools import split_ms

'''
Identify the continuum and line SPWs and split into separate MSs and
directories.
'''

mySDM = sys.argv[-4]
# Split out the lines, continuum or both
split_type = sys.argv[-3]
# Set whether to reindex the SPWs or not.
reindex_spws = True if sys.argv[-2] == "True" else False

include_rrls = True if sys.argv[-1] == "True" else False

ms_active = mySDM + ".ms"

print("Given inputs:")
print("SDM: {}".format(mySDM))
print("Splitting ms into: {}".format(split_type))

if not os.path.exists(ms_active):
    importasdm(asdm=mySDM, vis=ms_active, ocorr_mode='co',
               applyflags=True, savecmds=True, tbuff=7.5,
               outfile='{}.flagonline.txt'.format(mySDM),
               createmms=False)
else:
    print("MS already exists. Skipping importasdm")

# We're naming the parent file with the target, config,
# trackname and/or date. This keeps that info without explicitly
# needing to pass into this script
parentdir = os.getcwd().split("/")[-1]

# Only keep continuum SPWs as backup for 20A-346
# Otherwise drop for running on the archival projects
if '20A-346' in ms_active:
    keep_backup_continuum = True
else:
    keep_backup_continuum = False

split_ms(ms_active,
         outfolder_prefix=parentdir,
         split_type=split_type,
         continuum_kwargs={"baseband": 'both'},
         line_kwargs={"include_rrls": include_rrls,
                      "keep_backup_continuum": keep_backup_continuum},
         reindex=reindex_spws,
         overwrite=False)
