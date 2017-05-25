#!/usr/bin/env python

import copy

import numpy as np

from openquake.hazardlib.gsim.base import GMPE
from openquake.hazardlib import const
from openquake.hazardlib.imt import PGA, PGV, SA

from shakelib.grind.conversions.imt.newmark_hall_1982 import NewmarkHall1982
from shakelib.grind.conversions.imc.beyer_bommer_2006 import BeyerBommer2006
from shakelib.grind.sites import Sites

from shakelib.grind.gmpe_sets import nshmp14_acr
from shakelib.grind.gmpe_sets import nshmp14_scr_rlme
from shakelib.grind.gmpe_sets import nshmp14_scr_grd
from shakelib.grind.gmpe_sets import nshmp14_sub_i
from shakelib.grind.gmpe_sets import nshmp14_sub_s


class DualDistanceWeights(GMPE):
    """
    This class is a wrapper around the MultiGMPE class, which allows for the
    GMPE list and their weights to vary with distance. Only two sets of 
    GMPEs/weights are currently supported.
    """

    DEFINED_FOR_TECTONIC_REGION_TYPE = None
    DEFINED_FOR_INTENSITY_MEASURE_TYPES = None
    DEFINED_FOR_INTENSITY_MEASURE_COMPONENT = None
    DEFINED_FOR_STANDARD_DEVIATION_TYPES = None
    REQUIRES_SITES_PARAMETERS = None
    REQUIRES_RUPTURE_PARAMETERS = None
    REQUIRES_DISTANCES = None

    def get_mean_and_stddevs(self, sites, rup, dists, imt, stddev_types):
        """
        See superclass `method <http://docs.openquake.org/oq-hazardlib/master/gsim/index.html#openquake.hazardlib.gsim.base.GroundShakingIntensityModel.get_mean_and_stddevs>`__. 
        """

        # Small-distance MultiGMPE:
        lnmu, lnsd = self.mgmpe_small.get_mean_and_stddevs(
            sites, rup, dists, imt, stddev_types)

        # Large-distance MultiGMPE:
        if self.mgmpe_large is not None:
            lnmu_large, lnsd_large = self.mgmpe_large.get_mean_and_stddevs(
                sites, rup, dists, imt, stddev_types)

            # Stomp on lnmu and lnsd at large distances
            dist_cutoff = self.dist_cutoff
            lnmu[dists.rjb > dist_cutoff] = lnmu_large[dists.rjb > dist_cutoff]
            for i in range(len(lnsd)):
                lnsd[i][dists.rjb > dist_cutoff] = \
                    lnsd_large[i][dists.rjb > dist_cutoff]

        return lnmu, lnsd

    @classmethod
    def from_set_name(cls, set_name, imt = None):
        """
        Construct a DualDistanceWeights instance from set_name.

        Args:
            set_name (str): String indicating what GMPE set to use; valid 
                options are 'nshmp14_acr', 'nshmp14_scr_rlme', 
                'nshmp14_scr_grd', 'nshmp14_sub_i', 'nshmp14_sub_s'. The meaning
                of these strings is found in shakelib.grind.gmpe_sets.
            imt (IMT): Optional OQ IMT instance for filtering GMPE lists.

        """

        self = cls()
        self.set_name = set_name

        if set_name == 'nshmp14_acr':
            gmpes, wts, wts_large_dist, dist_cutoff, site_gmpes = \
                nshmp14_acr.get_weights()
        elif set_name == 'nshmp14_scr_rlme':
            gmpes, wts, wts_large_dist, dist_cutoff, site_gmpes = \
                nshmp14_scr_rlme.get_weights()
        elif set_name == 'nshmp14_scr_grd':
            gmpes, wts, wts_large_dist, dist_cutoff, site_gmpes = \
                nshmp14_scr_grd.get_weights()
        elif set_name == 'nshmp14_sub_i':
            gmpes, wts, wts_large_dist, dist_cutoff, site_gmpes = \
                nshmp14_sub_i.get_weights()
        elif set_name == 'nshmp14_sub_s':
            gmpes, wts, wts_large_dist, dist_cutoff, site_gmpes = \
                nshmp14_sub_s.get_weights()
        else:
            raise Exception("Unsupported value of set_name.")

        #-----------------------------------------------------------------------
        # Small-distance GMPE and weights
        #-----------------------------------------------------------------------

        # Remove GMPEs not applicable to this IMT and redistribute weights
        if imt is not None:
            sgmpe, swts = filter_gmpe_list(gmpes, wts, imt)
        else:
            sgmpe, swts = gmpes, wts

        self.mgmpe_small = MultiGMPE.from_list(
            sgmpe, swts, default_gmpes_for_site = site_gmpes)

        #-----------------------------------------------------------------------
        # Large-distance GMPE and weights
        #-----------------------------------------------------------------------
        if wts_large_dist is not None:
            # Remove GMPEs not applicable to this IMT and redistribute weights
            if imt is not None:
                sgmpe_large, swts_large = filter_gmpe_list(
                    gmpes, wts_large_dist, imt)
            else:
                sgmpe_large = gmpes
                swts_large = wts_large_dist
            self.mgmpe_large = MultiGMPE.from_list(
                sgmpe_large, swts_large, default_gmpes_for_site = site_gmpes)
            self.dist_cutoff = dist_cutoff
        else:
            self.mgmpe_large = None
            self.dist_cutoff = None
        return self


class MultiGMPE(GMPE):
    """
    Implements a GMPE that is the combination of multiple GMPEs.

    To do

        * Allow site to be based on a model that isn't a GMPE (e.g., 
          Borcherdt). 

    """

    DEFINED_FOR_TECTONIC_REGION_TYPE = None
    DEFINED_FOR_INTENSITY_MEASURE_TYPES = None
    DEFINED_FOR_INTENSITY_MEASURE_COMPONENT = None
    DEFINED_FOR_STANDARD_DEVIATION_TYPES = None
    REQUIRES_SITES_PARAMETERS = None
    REQUIRES_RUPTURE_PARAMETERS = None
    REQUIRES_DISTANCES = None

    def get_mean_and_stddevs(self, sites, rup, dists, imt, stddev_types):
        """
        See superclass `method <http://docs.openquake.org/oq-hazardlib/master/gsim/index.html#openquake.hazardlib.gsim.base.GroundShakingIntensityModel.get_mean_and_stddevs>`__. 
        """

        #-----------------------------------------------------------------------
        # Sort out shapes of sites and dists elements
        #-----------------------------------------------------------------------

        shapes = []
        for k, v in sites.__dict__.items():
            if (k is not 'lons') and (k is not 'lats'):
                shapes.append(v.shape)
        for k, v in dists.__dict__.items():
            if (k is not 'lons') and (k is not 'lats'):
                shapes.append(v.shape)

        shapeset = set(shapes)
        if len(shapeset) != 1:
            raise Exception('All sites and dists elements must have same shape.')
        else:
            orig_shape = list(shapeset)[0]

        # Need to turn all 2D arrays into 1D arrays because of
        # inconsistencies in how arrays are handled in OpenQuake.
        for k, v in dists.__dict__.items():
            if (k is not 'lons') and (k is not 'lats'):
                dists.__dict__[k] = np.reshape(dists.__dict__[k], (-1,))
        for k, v in sites.__dict__.items():
            if (k is not 'lons') and (k is not 'lats'):
                sites.__dict__[k] = np.reshape(sites.__dict__[k], (-1,))


        #-----------------------------------------------------------------------
        # These are arrays to hold the weighted combination of the GMPEs
        #-----------------------------------------------------------------------
        lnmu = np.zeros_like(sites.vs30)
        sd_avail = self.DEFINED_FOR_STANDARD_DEVIATION_TYPES
        if not sd_avail.issuperset(set(stddev_types)):
            raise Exception("Requested an unavailable stddev_type.")
        
        lnsd2 = [np.zeros_like(sites.vs30) for a in stddev_types]

        for i in range(len(self.GMPES)):
            #-------------------------------------------------------------------
            # Loop over GMPE list
            #-------------------------------------------------------------------

            gmpe = self.GMPES[i]

            sites = MultiGMPE.set_sites_depth_parameters(sites, gmpe)

            #-------------------------------------------------------------------
            # Evaluate GMPEs
            #-------------------------------------------------------------------

            gmpe_imts = [imt.__name__ for imt in \
                         gmpe.DEFINED_FOR_INTENSITY_MEASURE_TYPES]
            if (isinstance(imt, PGV)) and ("PGV" not in gmpe_imts):
                #---------------------------------------------------------------
                # If IMT is PGV and PGV is not given by the GMPE, then
                # convert from PSA10.
                #---------------------------------------------------------------
                if self.HAS_SITE[i] is True:
                    psa10, psa10sd = gmpe.get_mean_and_stddevs(
                        sites, rup, dists, SA(1.0), stddev_types)
                else:
                    lamps = self.get_site_factors(
                        sites, rup, dists, SA(1.0), default = True)
                    psa10, psa10sd = gmpe.get_mean_and_stddevs(
                        sites, rup, dists, SA(1.0), stddev_types)
                    psa10 = psa10 + lamps

                lmean, lsd = NewmarkHall1982.psa102pgv(psa10, psa10sd[0])
            else:
                if self.HAS_SITE[i] is True:
                    lmean, lsd = gmpe.get_mean_and_stddevs(
                        sites, rup, dists, imt, stddev_types)
                else:
                    lamps = self.get_site_factors(
                        sites, rup, dists, imt, default = True)
                    lmean, lsd = gmpe.get_mean_and_stddevs(
                        sites, rup, dists, imt, stddev_types)
                    lmean = lmean + lamps

            #-------------------------------------------------------------------
            # Convertions due to component definition
            #-------------------------------------------------------------------

            imc_in = gmpe.DEFINED_FOR_INTENSITY_MEASURE_COMPONENT
            imc_out = self.DEFINED_FOR_INTENSITY_MEASURE_COMPONENT
            lmean = BeyerBommer2006.ampIMCtoIMC(lmean, imc_in, imc_out, imt)
            for j in range(len(lnsd2)):
                lsd[j] = BeyerBommer2006.sigmaIMCtoIMC(
                    lsd[j], imc_in, imc_out, imt)

            #-------------------------------------------------------------------
            # Compute weighted mean and sd
            #-------------------------------------------------------------------

            lnmu = lnmu + self.WEIGHTS[i] * lmean

            # Note: the lnsd2 calculation isn't complete until we drop out of
            # this loop and substract lnmu**2
            for j in range(len(lnsd2)):
                lnsd2[j] = lnsd2[j] + self.WEIGHTS[i] * (lmean**2 + lsd[j]**2)

        for j in range(len(lnsd2)):
            lnsd2[j] = lnsd2[j] - lnmu**2

        lnsd = [np.sqrt(a) for a in lnsd2]

        # Undo reshapes of inputs
        for k, v in dists.__dict__.items():
            if (k is not 'lons') and (k is not 'lats'):
                dists.__dict__[k] = np.reshape(dists.__dict__[k], orig_shape)
        for k, v in sites.__dict__.items():
            if (k is not 'lons') and (k is not 'lats'):
                sites.__dict__[k] = np.reshape(sites.__dict__[k], orig_shape)

        # Reshape output
        lnmu = np.reshape(lnmu, orig_shape)
        for i in range(len(lnsd)):
            lnsd[i] = np.reshape(lnsd[i], orig_shape)

        return lnmu, lnsd

    @classmethod
    def from_list(cls, gmpes, weights, imc = const.IMC.GREATER_OF_TWO_HORIZONTAL,
                  default_gmpes_for_site = None,
                  default_gmpes_for_site_weights = None, 
                  reference_vs30 = 760):
        """
        Construct a MultiGMPE instance from lists of GMPEs and weights.

        :param gmpes:
            List of OpenQuake 
            `GMPE <http://docs.openquake.org/oq-hazardlib/master/gsim/index.html#built-in-gsims>`__ 
            instances.

        :param weights:
            List of weights; must sum to 1.0.

        :param imc: Requested intensity measure component. Must be one listed
            `here <http://docs.openquake.org/oq-hazardlib/master/const.html?highlight=imc#openquake.hazardlib.const.IMC>`__.
            The amplitudes returned by the GMPEs will be converted to this IMT. 
            Default is 'GREATER_OF_TWO_HORIZONTAL', which is used by ShakeMap. 
            See discussion in `this section <http://usgs.github.io/shakemap/tg_choice_of_parameters.html#use-of-peak-values-rather-than-mean>`__
            of the ShakeMap manual. 

        :param default_gmpes_for_site:
            Optional list of OpenQuake GMPE instance to use as a site term for
            any of the GMPEs that do not have a site term. 

            Notes:

                * We do not check for consistency in the reference rock 
                  defintion, so the user nees to be aware of this issue and holds
                  responsibiilty for ensuring compatibility. 
                * We check whether or not a GMPE has a site term by checking the
                  REQUIRES_SITES_PARAMETERS slot for vs30.

        :param default_gmpes_for_site_weights:
            Weights for default_gmpes_for_site. Must sum to one and be same
            length as default_gmpes_for_site. If None, then weights are set to
            be equal. 

        :param reference_vs30:
            Reference rock Vs30 in m/s. We do not check that this matches the
            reference rock in the GMPEs so this is the responsibility of the
            user.

        """

        #-----------------------------------------------------------------------
        # Check that GMPE weights sum to 1.0:
        #-----------------------------------------------------------------------

        if np.abs(np.sum(weights) - 1.0) > 1e-7:
            raise Exception('Weights must sum to one.')

        #-----------------------------------------------------------------------
        # Check that length of GMPE weights equals length of gmpe list
        #-----------------------------------------------------------------------

        if len(weights) != len(gmpes):
            raise Exception('Length of weights must match length of GMPE list.')

        #-----------------------------------------------------------------------
        # Check that gmpes is a list of OQ GMPE instances
        #-----------------------------------------------------------------------

        for g in gmpes:
            if not isinstance(g, GMPE):
                raise Exception("\"%s\" is not a GMPE instance." % g)

        self = cls()
        self.GMPES = gmpes
        self.WEIGHTS = weights

        #-----------------------------------------------------------------------
        # Check that GMPEs all are for the same tectonic region,
        # otherwise raise exception.
        #-----------------------------------------------------------------------

        tmp = set([i.DEFINED_FOR_TECTONIC_REGION_TYPE for i in gmpes])
        if len(tmp) == 1:
            self.DEFINED_FOR_TECTONIC_REGION_TYPE = \
                gmpes[0].DEFINED_FOR_TECTONIC_REGION_TYPE
        else:
            raise Exception('gmpes are not all for the same tectonic region.')

        #-----------------------------------------------------------------------
        # Combine the intensity measure types. This is problematic:
        #   - Logically, we should only include the intersection of the sets
        #     of imts for the different GMPEs.
        #   - In practice, this is not feasible because most GMPEs in CEUS and
        #     subduction zones do not have PGV.
        #   - So instead we will use the union of the imts and then convert
        #     to get the missing imts later in get_mean_and_stddevs.
        #-----------------------------------------------------------------------

        imts = [g.DEFINED_FOR_INTENSITY_MEASURE_TYPES for g in gmpes]
        self.DEFINED_FOR_INTENSITY_MEASURE_TYPES = set.union(*imts)

        #-----------------------------------------------------------------------
        # For VirtualIPE class, we also want to know if ALL of the GMPEs are
        # defined for PGV, in which case we will convert from PGV to MI,
        # otherwise use PGA or Sa.
        #-----------------------------------------------------------------------
        haspgv = [PGV in g.DEFINED_FOR_INTENSITY_MEASURE_TYPES for g in gmpes]
        self.ALL_GMPES_HAVE_PGV = all(haspgv)

        #-----------------------------------------------------------------------
        # Store intensity measure types for conversion in get_mean_and_stddevs.
        #---------------------------------------------------------
        self.IMCs = [g.DEFINED_FOR_INTENSITY_MEASURE_COMPONENT for g in gmpes]

        #-----------------------------------------------------------------------
        # Store the component
        #-----------------------------------------------------------------------
        self.DEFINED_FOR_INTENSITY_MEASURE_COMPONENT = imc

        #-----------------------------------------------------------------------
        # Intersection of GMPE standard deviation types
        #-----------------------------------------------------------------------
        stdlist = [set(g.DEFINED_FOR_STANDARD_DEVIATION_TYPES) for g in gmpes]
        self.DEFINED_FOR_STANDARD_DEVIATION_TYPES = \
            set.intersection(*stdlist)

        #-----------------------------------------------------------------------
        # Need union of site parameters, but it is complicated by the
        # different depth parameter flavors.
        #-----------------------------------------------------------------------
        sitepars = [g.REQUIRES_SITES_PARAMETERS for g in gmpes]
        self.REQUIRES_SITES_PARAMETERS = set.union(*sitepars)

        #-----------------------------------------------------------------------
        # Construct a list of whether or not each GMPE has a site term
        #-----------------------------------------------------------------------
        self.HAS_SITE = ['vs30' in g.REQUIRES_SITES_PARAMETERS for g in gmpes]

        #-----------------------------------------------------------------------
        # Checks and sort out defaults
        #-----------------------------------------------------------------------

        # things to check if default_gmpes_for_site is provided
        if default_gmpes_for_site is not None:
            # check that default_gmpe_for_site are OQ GMPEs or None
            for g in default_gmpes_for_site:
                if not isinstance(g, GMPE):
                    raise Exception("\"%s\" is not a GMPE instance." % g)

            # apply default weights if necessary
            if default_gmpes_for_site_weights is None:
                n = len(default_gmpes_for_site)
                default_gmpes_for_site_weights = [1/n]*n

        # Things to check if one or more GMPE does not have a site term
        if not all(self.HAS_SITE):
            # Raise an exception if no default site is provided
            if default_gmpes_for_site is None:
                raise Exception('Must provide default_gmpes_for_site if one or'\
                                ' more GMPE does not have site term.')

            # check that length of default_gmpe_for_site matches length of
            # default_gmpe_for_site_weights
            if len(default_gmpes_for_site_weights) != \
               len(default_gmpes_for_site):
                raise Exception('Length of default_gmpes_for_site_weights must'\
                                ' match length of default_gmpes_for_site list.')

            # check weights sum to one if needed
            if not all(self.HAS_SITE):
                if np.sum(default_gmpes_for_site_weights) != 1.0:
                    raise Exception('default_gmpes_for_site_weights must sum'\
                                    ' to one.')

        self.DEFAULT_GMPES_FOR_SITE = default_gmpes_for_site
        self.DEFAULT_GMPES_FOR_SITE_WEIGHTS = default_gmpes_for_site_weights
        self.REFERENCE_VS30 = reference_vs30

        #-----------------------------------------------------------------------
        # Union of rupture parameters
        #-----------------------------------------------------------------------
        ruppars = [g.REQUIRES_RUPTURE_PARAMETERS for g in gmpes]
        self.REQUIRES_RUPTURE_PARAMETERS = set.union(*ruppars)

        #-----------------------------------------------------------------------
        # Union of distance parameters
        #-----------------------------------------------------------------------
        distpars = [g.REQUIRES_DISTANCES for g in gmpes]
        self.REQUIRES_DISTANCES = set.union(*distpars)

        return self

    def get_site_factors(self, sites, rup, dists, imt, default = False):
        """
        Method for computing site amplification factors from the defalut GMPE
        to be applied to GMPEs which do not have a site term. 

        **NOTE** Amps are calculated in natural log space and so the ln(amp)
        is returned. 

        :param sites:
            Instance of SitesContext. 
        :param rup:
            Instance of RuptureContext.
        :param dists:
            Instance of DistancesContext.
        :param imt:
            An instance openquake.hazardlib.imt.
        :param default:
            Boolean of whether or not to return the amplificaiton factors for 
            the gmpes or default_gmpes_for_site. This argument is primarily only 
            intended to be used internally for when we just need to access the 
            default amplifications to apply to those GMPEs that do not have site
            terms. 
        """

        #-----------------------------------------------------------------------
        # Make reference sites context
        #-----------------------------------------------------------------------

        ref_sites = copy.deepcopy(sites)
        ref_sites.vs30 = np.ones_like(sites.vs30) * self.REFERENCE_VS30

        #-----------------------------------------------------------------------
        # If default True, construct new MultiGMPE with default GMPE/weights
        #-----------------------------------------------------------------------
        if default is True:
            tmp = MultiGMPE.from_list(
                self.DEFAULT_GMPES_FOR_SITE,
                self.DEFAULT_GMPES_FOR_SITE_WEIGHTS,
                self.DEFINED_FOR_INTENSITY_MEASURE_COMPONENT)

        #-----------------------------------------------------------------------
        # If default False, just use self
        #-----------------------------------------------------------------------
        else:
            tmp = self

        lmean, lsd = tmp.get_mean_and_stddevs(sites,
            rup, dists, imt, tmp.DEFINED_FOR_STANDARD_DEVIATION_TYPES)
        lmean_ref, lsd = tmp.get_mean_and_stddevs(ref_sites,
            rup, dists, imt, tmp.DEFINED_FOR_STANDARD_DEVIATION_TYPES)

        lamps = lmean - lmean_ref

        return lamps

    @staticmethod
    def set_sites_depth_parameters(sites, gmpe):
        """
        Need to select the appropriate z1pt0 value for different GMPEs.
        Note that these are required site parameters, so even though
        OQ has these equations built into the class in most cases. 
        I have submitted an issue to OQ requesting subclasses of these
        methods that do not require the depth parameters in the
        SitesContext to make this easier.

        :param sites:
            A sites context.
        :param gmpe:
            A GMPE instance.

        :returns:
            A sites context with the depth parameters set for the
            requested GMPE. 
        """

        sites = Sites._addDepthParameters(sites)

        if gmpe == 'AbrahamsonEtAl2014()':
            sites.z1pt0 = sites.z1pt0_ask14_cal
        if gmpe == 'ChiouYoungs2014()':
            # Also BooreEtAl2014() if using subclass with depth parameter
            sites.z1pt0 = sites.z1pt0_cy14_cal
        if gmpe == 'CampbellBozorgnia2014()':
            sites.z2pt5 = sites.z2pt5_cb14_cal
        if gmpe == 'ChiouYoungs2008()':
            sites.z1pt0 = sites.z1pt0_cy08
        if gmpe == 'CampbellBozorgnia2008()':
            sites.z2pt5 = sites.z2pt5_cb07

        return sites


def filter_gmpe_list(gmpes, wts, imt):
    """
    Method to remove GMPEs from the GMPE list that are not applicable
    to a specific IMT. Rescales the weights to sum to one. 

    Args:
        gmpes (list): List of GMPE instances. 
        wts (list): List of floats indicating the weight of the GMPEs. 

    Returns:
        tuple: List of GMPE instances and list of weights. 

    """
    per_max = [np.max(get_gmpe_sa_periods(g)) for g in gmpes]
    per_min = [np.min(get_gmpe_sa_periods(g)) for g in gmpes]
    if imt == PGA():
        sgmpe = [g for g in gmpes if imt in 
                 get_gmpe_coef_table(g).non_sa_coeffs]
        swts = [w for g, w in zip(gmpes, wts) if imt in 
                get_gmpe_coef_table(g).non_sa_coeffs]
    elif(imt == PGV()):
        sgmpe = []
        swts = []
        for i in range(len(gmpes)):
            if (imt in get_gmpe_coef_table(gmpes[i]).non_sa_coeffs) or\
               (per_max[i] >= 1.0 and per_min[i] <= 1.0):
               sgmpe.append(gmpes[i])
               swts.append(wts[i])
    else:
        per = imt.period
        sgmpe = []
        swts = []
        for i in range(len(gmpes)):
            if (per_max[i] >= per and per_min[i] <= per):
               sgmpe.append(gmpes[i])
               swts.append(wts[i])

    if len(sgmpe) == 0:
        raise Exception('No applicable GMPEs from GMPE list for %s' %val)

    # Scale weights to sum to one
    swts = np.array(swts)
    swts = swts/np.sum(swts)

    return sgmpe, swts



def get_gmpe_sa_periods(gmpe):
    """
    Method to extract the SA periods defined by a GMPE. 

    Args: 
        gmpe (GMPE): A GMPE instance. 

    Retunrs:
        list: List of periods. 

    """
    ctab = get_gmpe_coef_table(gmpe).sa_coeffs
    ilist = list(ctab.keys())
    per = [i.period for i in ilist]
    return per

def get_gmpe_coef_table(gmpe):
    """
    Method for finding the (or "a") GMPE table. If there are more than
    one, then the first one found is returned. This is okay when using
    check for the presence of PGA/PGV or the range of spectral periods
    because presumably this is consistent across all tables for a given 
    GMPE. 

    Notes:

      *  The reason for the complexity here is that some of the 
         OQ GMPE classes do not use the COEFFS attribute name
         for the table. So we have to look for it. We 
      *  We are also assuming that if there are more than one 
         coefficient table, the range of periods will be the 
         same across all of the tables. 
    """
    stuff = gmpe.__dir__()
    coef_stuff = [s for s in stuff if 'COEFFS' in s]
    coef_stuff = coef_stuff[0]

    cobj = getattr(gmpe, coef_stuff)
    return cobj

