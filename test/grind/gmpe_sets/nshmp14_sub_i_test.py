#!/usr/bin/env python

import os
import sys

from openquake.hazardlib.gsim.atkinson_boore_2003 import AtkinsonBoore2003SInter
from openquake.hazardlib.gsim.zhao_2006 import ZhaoEtAl2006SInter
from openquake.hazardlib.gsim.atkinson_macias_2009 import AtkinsonMacias2009
from openquake.hazardlib.gsim.abrahamson_2015 import AbrahamsonEtAl2015SInter

homedir = os.path.dirname(os.path.abspath(__file__))  # where is this script?
shakedir = os.path.abspath(os.path.join(homedir, '..', '..', '..'))
sys.path.insert(0, shakedir)

from shakelib.grind.gmpe_sets import nshmp14_sub_i


def test_nshmp14_sub_i():
    gmpes, wts, wts_large_dist, dist_cutoff, site_gmpes = \
        nshmp14_sub_i.get_weights()

    assert gmpes == \
        ['AtkinsonBoore2003SInter()',
         'ZhaoEtAl2006SInter()',
         'AtkinsonMacias2009()',
         'AbrahamsonEtAl2015SInter()']

    assert wts == [0.1, 0.3, 0.3, 0.3]

    assert wts_large_dist is None

    assert dist_cutoff is None

#    assert site_gmpes == 

if __name__ == '__main__':
    test_nshmp14_sub_i()
