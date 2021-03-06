"""This module contains strategies to convert a score breakdown to
the total score. This is commonly specified via the
--combination_scheme parameter.

TODO: The breakdown2score interface is not very elegant, and has some
      overlap with the interpolation_strategy implementations.
"""

from cam.sgnmt import utils
from cam.sgnmt.decoding.core import Decoder
import numpy as np
import logging


def breakdown2score_sum(working_score, score_breakdown, full=False):
    """Implements the combination scheme 'sum' by always returning
    ``working_score``. 
    
    Args:
        working_score (float): Working combined score, which is the 
                               weighted sum of the scores in
                               ``score_breakdown``
        score_breakdown (list): Breakdown of the combined score into
                                predictor scores (not used).
        full (bool): If True, reevaluate all time steps. If False,
                     assume that this function has been called in the
                      previous time step (not used).
    
    Returns:
        float. Returns ``working_score``
    """
    return working_score


def breakdown2score_length_norm(working_score, score_breakdown, full=False):
    """Implements the combination scheme 'length_norm' by normalizing
    the sum of the predictor scores by the length of the current 
    sequence (i.e. the length of ``score_breakdown``). 
    TODO could make more efficient use of ``working_score``
    
    Args:
        working_score (float): Working combined score, which is the 
                               weighted sum of the scores in
                               ``score_breakdown``. Not used.
        score_breakdown (list): Breakdown of the combined score into
                                predictor scores
        full (bool): If True, reevaluate all time steps. If False,
                     assume that this function has been called in the
                      previous time step (not used).
    
    Returns:
        float. Returns a length normalized ``working_score``
    """
    score = sum([Decoder.combi_arithmetic_unnormalized(s) 
                        for s in score_breakdown])
    return score / len(score_breakdown)


def breakdown2score_bayesian(working_score, score_breakdown, full=False):
    """This realizes score combination following the Bayesian LM 
    interpolation scheme from (Allauzen and Riley, 2011)
    
      Bayesian Language Model Interpolation for Mobile Speech Input
    
    By setting K=T we define the predictor weights according the score
    the predictors give to the current partial hypothesis. The initial
    predictor weights are used as priors. 
    TODO could make more efficient use of ``working_score``
    
    Args:
        working_score (float): Working combined score, which is the 
                               weighted sum of the scores in
                               ``score_breakdown``. Not used.
        score_breakdown (list): Breakdown of the combined score into
                                predictor scores
        full (bool): If True, reevaluate all time steps. If False,
                     assume that this function has been called in the
                      previous time step.
    
    Returns:
        float. Bayesian interpolated predictor scores
    """
    if not score_breakdown or working_score == utils.NEG_INF:
        return working_score
    if full:
        acc = []
        alphas = [] # list of all alpha_i,k
        # Write priors to alphas
        for (p, w) in score_breakdown[0]:
            alphas.append(np.log(w))
        for pos in score_breakdown: # for each position in the hypothesis
            for k, (p, w) in enumerate(pos): 
                alphas[k] += p
            alpha_part = utils.log_sum(alphas)
            scores = [alphas[k] - alpha_part + p 
                    for k, (p, w) in enumerate(pos)]
            acc.append(utils.log_sum(scores)) 
        return sum(acc)
    else: # Incremental: Alphas are in predictor weights
        if len(score_breakdown) == 1:
            scores = [np.log(w) + p for p, w in score_breakdown[0]]
            return utils.log_sum(scores)
        priors = [s[1] for s in score_breakdown[0]]
        last_score = sum([w * s[0] 
                          for w, s in zip(priors, score_breakdown[-1])])
        working_score -= last_score
        # Now, working score does not include the last time step anymore
        # Compute updated alphas
        alphas = [np.log(p) for p in priors]
        for pos in score_breakdown[:-1]:
            for k, (p, _) in enumerate(pos):
                alphas[k] += p
        alpha_part = utils.log_sum(alphas)
        scores = [alphas[k] - alpha_part + p 
                for k, (p, w) in enumerate(score_breakdown[-1])]
        updated_breakdown = [(p, np.exp(alphas[k] - alpha_part))
                for k, (p, w) in enumerate(score_breakdown[-1])]
        score_breakdown[-1] = updated_breakdown
        working_score += utils.log_sum(scores)
        return working_score


def breakdown2score_bayesian_loglin(working_score, score_breakdown, full=False):
    """Like bayesian combination scheme, but uses loglinear model
    combination rather than linear interpolation weights
   
    TODO: Implement incremental version of it, write weights into breakdowns.
    """
    if not score_breakdown:
        return working_score
    acc = []
    prev_alphas = [] # list of all alpha_i,k
    # Write priors to alphas
    for (p, w) in score_breakdown[0]:
        prev_alphas.append(np.log(w))
    for pos in score_breakdown: # for each position in the hypothesis
        alphas = []
        sub_acc = []
        # for each predictor (p: p_k(w_i|h_i), w: prior p(k))
        for k, (p, w) in enumerate(pos): 
            alpha = prev_alphas[k] + p
            alphas.append(alpha)
            sub_acc.append(p + alpha)
        acc.append(utils.log_sum(sub_acc) - utils.log_sum(alphas))
        prev_alphas = alphas
    return sum(acc)

