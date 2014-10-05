"""
Weight models for the Network GLM
"""
import numpy as np

import theano.tensor as T

import kayak as kyk

from component import Component
from pyglm.components.priors import create_prior


def create_weight_component(model, latent):
        type = model['network']['weight']['type'].lower()
        if type == 'constant':
            weight = TheanoConstantWeightModel(model)
        elif type == 'gaussian':
            weight = TheanoGaussianWeightModel(model)
        else:
            raise Exception("Unrecognized weight model: %s" % type)
        return weight

def create_kayak_weight_component(model, latent):
        type = model['network']['weight']['type'].lower()
        if type == 'constant':
            weight = KayakConstantWeightModel(model)
        elif type == 'gaussian':
            weight = KayakGaussianWeightModel(model)
        else:
            raise Exception("Unrecognized weight model: %s" % type)
        return weight

class _WeightModelBase(Component):
    @property
    def W(self):
        raise NotImplementedError()

    def get_state(self):
        return {'W': self.W}

class TheanoConstantWeightModel(_WeightModelBase):
    def __init__(self, model):
        """ Initialize the filtered stim model
        """
        self.model = model
        N = model['N']

        prms = model['network']['weight']
        self.value = prms['value']
        
        # Define weight matrix
        self._W = self.value * T.ones((N,N))

        # Define log probability
        self._log_p = T.constant(0.0)

    @property
    def W(self):
        return self._W

    @property
    def log_p(self):
        return self._log_p


class KayakConstantWeightModel(_WeightModelBase):
    def __init__(self, model):
        """ Initialize the filtered stim model
        """
        self.model = model
        N = model['N']

        prms = model['network']['weight']
        self.value = prms['value']

        # Define weight matrix
        self._W = kyk.Constant(self.value * np.ones((N,N)))

        # Define log probability
        self._log_p = kyk.Constant(0.0)

    @property
    def W(self):
        return self._W

    @property
    def log_p(self):
        return self._log_p


class TheanoGaussianWeightModel(_WeightModelBase):
    def __init__(self, model):
        """ Initialize the filtered stim model
        """
        self.model = model
        N = model['N']
        prms = model['network']['weight']

        self.prior = create_prior(prms['prior'])

        # Implement refractory period by having negative mean on self loops
        if 'refractory_prior' in prms:
            #self.mu[np.diag_indices(N)] = prms['mu_refractory']
            self.refractory_prior = create_prior(prms['refractory_prior'])

            # Get the upper and lower diagonal indices so that we can evaluate
            # the log prob of the refractory weights separately from the
            # log prob of the regular weights
            self.diags = np.ravel_multi_index(np.diag_indices(N), (N,N))
            lower = np.ravel_multi_index(np.tril_indices(N,k=-1), (N,N))
            upper = np.ravel_multi_index(np.triu_indices(N,k=1), (N,N))
            self.nondiags = np.concatenate((lower, upper))

        # Define weight matrix
        self.W_flat = T.dvector(name='W')
        self._W = T.reshape(self.W_flat,(N,N))

        if hasattr(self, 'refractory_prior'):
            self._log_p = self.prior.log_p(self.W.take(self.nondiags)) + \
                         self.refractory_prior.log_p(self.W.take(self.diags))
        else:
            self._log_p = self.prior.log_p(self.W)

    @property
    def W(self):
        return self._W

    @property
    def log_p(self):
        return self._log_p

    def sample(self, acc):
        """
        return a sample of the variables
                """
        N = self.model['N']

        if hasattr(self, 'refractory_prior'):
            W = np.zeros((N,N))
            # W_diags = np.array([self.refractory_prior.sample() for n in np.arange(N)])
            W_diags = self.refractory_prior.sample(None, (N,) )
            # W_nondiags = np.array([self.prior.sample() for n in np.arange(N**2-N)])
            W_nondiags = self.prior.sample(None, (N**2-N,))
            np.put(W, self.diags,  W_diags)
            np.put(W, self.nondiags, W_nondiags)
            W_flat = np.reshape(W,(N**2,))
        else:
            W_flat = self.prior.sample(None, (N**2,))
            # W_flat = np.array([self.prior.sample()for n in np.arange(N**2)])

        return {str(self.W_flat): W_flat}

    def get_variables(self):
        """ Get the theano variables associated with this model.
        """
        return {str(self.W_flat): self.W_flat}



class KayakGaussianWeightModel(_WeightModelBase):
    def __init__(self, model):
        """ Initialize the filtered stim model
        """
        self.model = model
        self.N = model['N']
        prms = model['network']['weight']

        self.mu = prms['prior']['mu'] * np.ones((self.N,self.N))
        self.sigma = prms['prior']['sigma'] * np.ones((self.N,self.N))

        if 'refractory_prior' in prms:
            diags = np.diag_indices(self.N)
            self.mu[diags] = prms['refractory_prior']['mu']
            self.sigma[diags] = prms['refractory_prior']['sigma']

        self._W = kyk.Parameter(np.zeros((self.N,self.N)))

        # There is some weirdness with __mult__(np.ndarray, kyk.Differentiable))
        self._log_p = kyk.MatSum(kyk.Parameter(-0.5/self.sigma**2) * (self.W - self.mu)**2)

    @property
    def W(self):
        return self._W

    @property
    def log_p(self):
        return self._log_p

    def sample(self, acc):
        """
        return a sample of the variables
        """
        W = self.mu + self.sigma * np.random.randn(self.N,self.N)
        return { 'W' : W}

    def get_variables(self):
        """ Get the Kayak variables associated with this model.
        """
        return { 'W' : self.W }
