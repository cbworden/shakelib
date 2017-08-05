#!/usr/bin/env python

# stdlib imports
import os.path
import sys
import io
import json
import numpy as np

homedir = os.path.dirname(os.path.abspath(__file__))  # where is this script?
shakedir = os.path.abspath(os.path.join(homedir, '..', '..'))
sys.path.insert(0, shakedir)

from shakelib.grind.container import InputContainer, OutputContainer


def test_container():
    config = {'alliance': 'chaotic neutral',
              'race': 'Elf',
              'armor': 5,
              'class': 'Warrior',
              'intelligence': 10}
    datafile = os.path.join(os.path.expanduser('~'), 'test.hdf')
    rupturefile = os.path.join(homedir, 'container_data/Barkaetal02_fault.txt')
    event_text = """<?xml version="1.0" encoding="US-ASCII" standalone="yes"?>
<earthquake id="2008ryan" lat="30.9858" lon="103.3639" mag="7.9" year="2008"
month="05" day="12" hour="06" minute="28" second="01" timezone="GMT" depth="19.0"
locstring="EASTERN SICHUAN, CHINA" created="1211173621" otime="1210573681" type="" />"""
    eventfile = io.StringIO(event_text)
    datafiles = [os.path.join(
        homedir, 'container_data/northridge_stations_dat.xml')]
    container = InputContainer.loadFromInput(datafile, config, eventfile,
                                             datafiles=datafiles,
                                             rupturefile=rupturefile)
    station = container.getStationList()
    origin = container.getOrigin()
    rupture = container.getRupture()
    del container

    container2 = InputContainer.loadFromHDF(datafile)
    station = container2.getStationList()
    origin = container2.getOrigin()
    rupture = container2.getRupture()

def test_output_container():
    test_file = os.path.join(homedir, 'container_data', 'test.hdf')
    oc = OutputContainer.createEmpty(test_file)
    test_dict = { 'float': 2.5,
                  'int': 3,
                  'string': 'This is a test',
                  'list': [1, 2, 3],
                  'dict': {'name': 'Joe', 'age': 20},
                  'nparray': np.array([1., 2., 3.])}
    test_string = 'This is a string.'
    test_json = json.dumps({'thing': 'some json', 'stuff': [1, 2, 3]})
    test_array = np.array([[1., 2., 3.], [4., 5., 6.]])
    test_dset_metadata = {'nx': 100, 'ny': 200, 'an_array': np.array([1, 2, 3])}

    oc.addMetadata(test_dict)
    oc.addData(test_string, 'test_string')
    oc.addData(test_json, 'test_json')
    oc.addData(test_array, 'test_array', metadata=test_dset_metadata)
    oc.close()

    del oc

    oc = OutputContainer.loadFromHDF(test_file)
    td = oc.getMetadata()
    ts, tsmd = oc.getData('test_string')
    tj, tjmd = oc.getData('test_json')
    ta, tamd = oc.getData('test_array')

    oc.close()
    os.remove(test_file)

    assert set(td.keys()) == set(test_dict.keys())
    assert ts == test_string
    assert tj == test_json
    assert np.all(ta == test_array)
    assert set(tamd.keys()) == set(test_dset_metadata.keys())



if __name__ == '__main__':
    test_container()
    test_output_container()
