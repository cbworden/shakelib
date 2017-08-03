#!/bin/bash
echo $PATH

VENV=shakelib2
PYVER=3.5


DEPARRAY=(numpy=1.13.1 scipy=0.19.1 matplotlib=2.0.2 rasterio=1.0a9 pandas=0.20.3 h5py=2.7.0 gdal=2.1.4 pytest=3.2.0 pytest-cov=2.5.1 cartopy=0.15.1 fiona=1.7.8 numexpr=2.6.2 configobj=5.0.6 decorator=4.1.2)


# Turn off whatever other virtual environment user might be in
source deactivate

# Remove any previous virtual environments called shakelib2
CWD=`pwd`
cd $HOME;
conda remove --name $VENV --all -y
cd $CWD

conda create --name $VENV --yes python=$PYVER ${DEPARRAY[*]} -y

# Activate the new environment
source activate $VENV

# do pip installs of those things that are not available via conda.
# grab the bleeding edge for GEM hazardlib.  They have actual releases
# we can resort to if this becomes a problem.
curl --max-time 60 --retry 3 -L https://github.com/gem/oq-engine/archive/master.zip -o openquake.zip
pip -v install --no-deps openquake.zip
rm openquake.zip

pip -v install https://github.com/usgs/MapIO/archive/master.zip
pip -v install https://github.com/usgs/earthquake-impact-utils/archive/master.zip


# Tell the user they have to activate this environment
echo "Type 'source activate $VENV' to use this new virtual environment."
