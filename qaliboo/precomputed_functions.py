"""Precomputed functions

The instances exposed here are utilities to manage
 the sample datasets as domains and target functions
"""
import logging

import numpy as np

from examples import abstract_problem
from qaliboo import finite_domain, datasets


_log = logging.getLogger(__name__)
_log.setLevel(level=logging.DEBUG)


class _PrecomputedFunction(finite_domain.CPPFiniteDomain, abstract_problem.AbstractProblem):

    def __init__(self, dataset: datasets.Dataset):
        m = np.min(dataset.X, axis=0)
        M = np.max(dataset.X, axis=0)
        domain_bounds = np.vstack([m, M]).transpose()
        super().__init__(data=dataset.X.values,
                         search_domain=domain_bounds,
                         min_value=np.min(dataset.y))
        self._dataset = dataset

    @property
    def minimum(self):
        ix = np.argmin(self._dataset.y)
        return self._dataset.X.loc[ix].values

    def evaluate_true(self, x):
        distances, indexes, points = self.find_distances_indexes_closest_points(x)
        # if any(distances > 0.00001):
        #     _log.warning(f'POSSIBLE EVALUATION ERROR: The distance between the point in '
        #                  f'domain and the evaluated point is large')
        min_distance = np.min(distances)
        if min_distance == 0.0:
            _log.debug('There is at least one exact match')
        mask = distances == min_distance
        if np.sum(mask) == 1:
            _log.debug('Only one match, return it')
            values = self._dataset.y[indexes[mask]]
        else:
            _log.debug('Multiple matches, random pick...')
            indexes = indexes[mask]
            values = [self._dataset.y[np.random.choice(indexes)]]
        return np.array(values)


LiGen = _PrecomputedFunction(
    dataset=datasets.LiGen
)

Query26 = _PrecomputedFunction(
    dataset=datasets.Query26
)

StereoMatch = _PrecomputedFunction(
    dataset=datasets.StereoMatch
)
