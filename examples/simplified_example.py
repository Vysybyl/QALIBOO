import time

import numpy as np

from moe.optimal_learning.python import data_containers
from moe.optimal_learning.python.cpp_wrappers import log_likelihood_mcmc, optimization as cpp_optimization, knowledge_gradient, knowledge_gradient_mcmc
from moe.optimal_learning.python.python_version import optimization as py_optimization
from moe.optimal_learning.python import default_priors, repeated_domain

from examples import synthetic_functions, bayesian_optimization, finite_domain

###########################
# Constants
###########################
N_INITIAL_POINTS = 5
N_ITERATIONS = 1
N_POINTS_PER_ITERATION = 4  # The q- parameter
MODE = 'KG'  # 'EI' vs 'KG'
M_DOMAIN_DISCRETIZATION_SAMPLE_SIZE = 10  # M parameter


###########################
# Target function
###########################
objective_func_name = 'Parabolic with minimum at (2, 3)'
objective_func = synthetic_functions.ParabolicMinAtTwoAndThree()

###############################
# Initializing utility objects
###############################

# Various Gradient Descent parameters
py_sgd_params_ps = py_optimization.GradientDescentParameters(
    max_num_steps=1000,
    max_num_restarts=3,
    num_steps_averaged=15,
    gamma=0.7,
    pre_mult=1.0,
    max_relative_change=0.02,
    tolerance=1.0e-10)

cpp_sgd_params_ps = cpp_optimization.GradientDescentParameters(
    num_multistarts=1,
    max_num_steps=6,
    max_num_restarts=1,
    num_steps_averaged=3,
    gamma=0.0,
    pre_mult=1.0,
    max_relative_change=0.1,
    tolerance=1.0e-10)

KG_gradient_descent_params = cpp_optimization.GradientDescentParameters(
    num_multistarts=200,
    max_num_steps=50,
    max_num_restarts=2,
    num_steps_averaged=4,
    gamma=0.7,
    pre_mult=1.0,
    max_relative_change=0.5,
    tolerance=1.0e-10)

###########################
# Loading data in domain
###########################

# precomputed_sample_df = sklearn.datasets.load_diabetes(as_frame=True)['frame']
#
# # No need for bounds, BUT you might need to specify column names for first derivative, second derivative, etc.
# domain = moe_cpp.FiniteDomain(dataset=precomputed_sample_df, target_column=TARGET_COLUMN)

domain = finite_domain.FiniteDomain.Grid(np.arange(-5, 5, 0.1),
                                         np.arange(-5, 5, 0.1))

###########################
# Starting up the MCMC...
###########################

# > Algorithm 1.1: Initial Stage: draw `I` initial samples from a latin hypercube design in `A` (domain)

# Draw initial points from domain (as np array)
initial_points_array = domain.SamplePointsInDomain(objective_func._num_init_pts)
# Evaluate function in initial points
initial_points_value = np.array([objective_func.evaluate(pt) for pt in initial_points_array])
# Build points using custom container class
initial_points = [data_containers.SamplePoint(pt,
                                              [initial_points_value[num, i]
                                               for i in objective_func.observations],
                                              objective_func._sample_var)
                  for num, pt in enumerate(initial_points_array)]

# Build historical data container
initial_data = data_containers.HistoricalData(dim=objective_func._dim)

initial_data.append_sample_points(initial_points)

# initialize the model
# (It is completely unclear what these parameters mean)
n_prior_hyperparameters = 1 + objective_func._dim + objective_func.n_observations
n_prior_noises = objective_func.n_observations
prior = default_priors.DefaultPrior(n_prior_hyperparameters, n_prior_noises)

# noisy = False means the underlying function being optimized is noise-free
gp_loglikelihood = log_likelihood_mcmc.GaussianProcessLogLikelihoodMCMC(
    historical_data=initial_data,
    derivatives=objective_func.derivatives,
    prior=prior,
    chain_length=1000,
    burnin_steps=2000,
    n_hypers=2 ** 4,  # 16 random walkers
    noisy=False
)
gp_loglikelihood.train()

###########################
# Main cycle
###########################

# Algorithm 1.2: Main Stage: For `s` to `N`
for s in range(N_ITERATIONS):
    print(f"{MODE}, "
          f"{s}th iteration, "
          f"func={objective_func_name}, "
          f"q={N_POINTS_PER_ITERATION}")
    time1 = time.time()

    if MODE == 'KG':

        # > The q-KG algorithm will reduce to the parallel EI algorithm
        # > if function evaluations are noise-free
        # > and the final recommendation is restricted to the previous sampling decisions.

        # Run KG
        # > Algorithm 1.4: Solve the main equation:
        # > (find points (z∗1 , z∗2 , · · · , z∗q) that maximize the q-KG factor

        # > Par 5.3:
        # > In this paper, the discrete set A_n is not chosen statically,
        # > but evolves over time: specifically, we suggest drawing M samples
        # > from the global optima of the posterior distribution of the Gaussian
        # > process. This sample set, denoted by A_n^M, is then extended
        # > by the locations of previously sampled [=evaluated] points x(1:n)
        # > and the set of candidate points z(1:q)

        # So, the infinite domain A is replaced by a discrete set of points A_n (see above)
        discrete_pts_list = []

        qEI_next_points, _ = bayesian_optimization.qEI_generate_next_points_using_mcmc(
            gaussian_process_mcmc=gp_loglikelihood._gaussian_process_mcmc,
            search_domain=domain,
            gd_params=KG_gradient_descent_params,
            q=M_DOMAIN_DISCRETIZATION_SAMPLE_SIZE,
            mc_iterations=2 ** 10)

        for i, cpp_gaussian_process in enumerate(gp_loglikelihood.models):  # What are these models?

            eval_pts = domain.generate_uniform_random_points_in_domain(int(1e3))
            eval_pts = np.reshape(np.append(eval_pts,
                                            (cpp_gaussian_process.get_historical_data_copy()).points_sampled[:, :(gp_loglikelihood.dim)]),
                                  (eval_pts.shape[0] + cpp_gaussian_process.num_sampled, cpp_gaussian_process.dim))

            test = np.zeros(eval_pts.shape[0])
            ps_evaluator = knowledge_gradient.PosteriorMean(cpp_gaussian_process)
            for i, pt in enumerate(eval_pts):
                ps_evaluator.set_current_point(pt.reshape((1, gp_loglikelihood.dim)))
                test[i] = -ps_evaluator.compute_objective_function()

            initial_point = eval_pts[np.argmin(test)]

            ps_sgd_optimizer = cpp_optimization.GradientDescentOptimizer(
                domain,
                ps_evaluator,
                cpp_sgd_params_ps
            )

            report_point = knowledge_gradient.posterior_mean_optimization(
                ps_sgd_optimizer,
                initial_guess=initial_point,
                max_num_threads=4
            )

            discrete_pts_optima = np.reshape(np.append(qEI_next_points, report_point),
                                             (qEI_next_points.shape[0] + 1, cpp_gaussian_process.dim))
            discrete_pts_list.append(discrete_pts_optima)

        ps_evaluator = knowledge_gradient.PosteriorMean(gp_loglikelihood.models[0], 0)
        ps_sgd_optimizer = cpp_optimization.GradientDescentOptimizer(
            domain,
            ps_evaluator,
            cpp_sgd_params_ps
        )
        # KG method
        next_points, voi = bayesian_optimization.gen_sample_from_qkg_mcmc(
            gp_loglikelihood._gaussian_process_mcmc,
            gp_loglikelihood.models,
            ps_sgd_optimizer,
            domain,
            0,
            discrete_pts_list,
            KG_gradient_descent_params,
            N_POINTS_PER_ITERATION,
            num_mc=2 ** 7)


    else:  # method == 'EI':
        next_points, voi = bayesian_optimization.gen_sample_from_qei(
            gp_loglikelihood.models[0],
            domain,
            KG_gradient_descent_params,
            N_POINTS_PER_ITERATION,
            num_mc=2 ** 10
        )

    print(f"{MODE} takes {(time.time()-time1)} seconds")
    print("Suggests points:")
    print(next_points)

    # > ALgorithm 1.5: 5: Sample these points (z∗1 , z∗2 , · · · , z∗q)
    # > ...
    sampled_points = [data_containers.SamplePoint(pt,
                                                  objective_func.evaluate(pt)[objective_func.observations],
                                                  objective_func._sample_var)
                      for pt in next_points]

    time1 = time.time()

    # > ...
    # > re-train the hyperparameters of the GP by MLE
    # > and update the posterior distribution of f
    gp_loglikelihood.add_sampled_points(sampled_points)
    gp_loglikelihood.train()
    print(f"Retraining the model takes {time.time() - time1} seconds")
    time1 = time.time()

    # > Algorithm 1.7: Return the argmin of the average function `μ` currently estimated in `A`

    # In the current implementation, this argmin is found
    # and returned at every interaction (called "report_point").

    print("\nIteration finished successfully!")
    # print(f"The recommended point: {report_point}")
    # print(f"The recommended integer point: {np.round(report_point).astype(int)}")
    # print(f"Finding the recommended point takes {time.time()-time1} seconds")
    # print(f" {MODE}, VOI {voi}, best so far {objective_func.evaluate_true(report_point)[0]}")

# report the point
if MODE == 'KG':
    eval_pts = domain.generate_uniform_random_points_in_domain(int(1e4))
    eval_pts = np.reshape(np.append(eval_pts, (gp_loglikelihood.get_historical_data_copy()).points_sampled[:, :(gp_loglikelihood.dim)]),
                          (eval_pts.shape[0] + gp_loglikelihood._num_sampled, gp_loglikelihood.dim))

    post_mean = knowledge_gradient_mcmc.PosteriorMeanMCMC(
        gp_loglikelihood.models
    )

    test = np.zeros(eval_pts.shape[0])
    for i, pt in enumerate(eval_pts):
        post_mean.set_current_point(pt.reshape((1, gp_loglikelihood.dim)))
        test[i] = -post_mean.compute_objective_function()
    initial_point = eval_pts[np.argmin(test)].reshape((1, gp_loglikelihood.dim))

    repeated_domain = repeated_domain.RepeatedDomain(num_repeats=1,
                                                     domain=domain)
    ps_mean_opt = py_optimization.GradientDescentOptimizer(repeated_domain,
                                                           post_mean,
                                                           py_sgd_params_ps)
    report_point = py_optimization.multistart_optimize(ps_mean_opt,
                                                       initial_point,
                                                       num_multistarts=1)[0]

else:  # method == 'EI':
    cpp_gp = gp_loglikelihood.models[0]
    report_point = (cpp_gp.get_historical_data_copy()).points_sampled[np.argmin(cpp_gp._points_sampled_value[:, 0])]

report_point = report_point.ravel()

print("\nOptimization finished successfully!")
print(f"The recommended point: {report_point}")
print(f"The recommended integer point: {np.round(report_point).astype(int)}")
print(f"Finding the recommended point takes {time.time() - time1} seconds")
print(f" {MODE}, VOI {voi}, best so far {objective_func.evaluate_true(report_point)[0]}")
