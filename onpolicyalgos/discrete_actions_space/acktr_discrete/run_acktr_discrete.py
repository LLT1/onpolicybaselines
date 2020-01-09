#!/usr/bin/env python3
import argparse
import logging
import os
import tensorflow as tf
import gym
from baselines import logger
from baselines.common import set_global_seeds
from baselines import bench
from acktr_cont import learn
from policies import MultiCategoricalPolicy
from value_functions import NeuralNetValueFunction
import numpy as np

def train(env_id, num_timesteps, seed, kl, bins):
    env=gym.make(env_id)
    ob_dim = env.observation_space.shape[0]
    ac_dim = env.action_space.shape[0]
    import wrapper
    env = wrapper.discretizing_wrapper(env, K=bins)

    env = bench.Monitor(env, logger.get_dir() and os.path.join(logger.get_dir()))
    set_global_seeds(seed)
    env.seed(seed)
    gym.logger.setLevel(logging.WARN)

    with tf.Session(config=tf.ConfigProto()):
        with tf.variable_scope("vf"):
            vf = NeuralNetValueFunction(ob_dim, ac_dim)
        with tf.variable_scope("pi"):
            policy = MultiCategoricalPolicy(ob_dim, ac_dim, ac_space=env.action_space, bins=bins)

        learn(env, policy=policy, vf=vf,
            gamma=0.99, lam=0.97, timesteps_per_batch=2500,
            desired_kl=0.002,
            num_timesteps=num_timesteps, animate=False)

        env.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Run Mujoco benchmark.')
    parser.add_argument('--seed', help='RNG seed', type=int, default=0)
    parser.add_argument('--env', help='environment ID', type=str, default="Reacher-v1")
    parser.add_argument('--num-timesteps', type=int, default=int(1e6))
    parser.add_argument('--kl', type=float, default=0.002)
    parser.add_argument('--bins', type=int, default=11)
    args = parser.parse_args()
    logger.configure()
    train(args.env, num_timesteps=args.num_timesteps, seed=args.seed, kl=args.kl, bins=args.bins)