#!/bin/bash

mkdir simics-workspace
pushd simics-workspace
git clone git@gitlab.hcs.ufl.edu:F4/simics-p2020rdb
pushd simics-p2020rdb
rm -rf .git
popd
git clone git@gitlab.hcs.ufl.edu:F4/simics-a9x2
pushd simics-a9x2
rm -rf .git
popd
popd

rm .gitignore setup_apps.sh setup_bdi_tftp.sh setup_simics_workspace.sh
rm -rf .git

python -m compileall -l .
rm ./*.py
touch drseus.sh
printf '#!/bin/bash\npython drseus.pyc "$@"' > drseus.sh
chmod +x drseus.sh

pushd log
python -m compileall -l .
rm ./*.py
popd

rm package.sh
