import numpy as np
import tensorflow as tf
from utilskfac import conv, fc, dense, conv_to_fc, sample, kl_div
import baselines.common.tf_util as U

class CnnPolicy(object):

    def __init__(self, sess, ob_space, ac_space, nenv, nsteps, nstack, reuse=False):
        nbatch = nenv*nsteps
        nh, nw, nc = ob_space.shape
        ob_shape = (nbatch, nh, nw, nc*nstack)
        nact = ac_space.n
        X = tf.placeholder(tf.uint8, ob_shape) #obs
        with tf.variable_scope("model", reuse=reuse):
            h = conv(tf.cast(X, tf.float32)/255., 'c1', nf=32, rf=8, stride=4, init_scale=np.sqrt(2))
            h2 = conv(h, 'c2', nf=64, rf=4, stride=2, init_scale=np.sqrt(2))
            h3 = conv(h2, 'c3', nf=32, rf=3, stride=1, init_scale=np.sqrt(2))
            h3 = conv_to_fc(h3)
            h4 = fc(h3, 'fc1', nh=512, init_scale=np.sqrt(2))
            pi = fc(h4, 'pi', nact, act=lambda x:x)
            vf = fc(h4, 'v', 1, act=lambda x:x)

        v0 = vf[:, 0]
        a0 = sample(pi)
        self.initial_state = [] #not stateful

        def step(ob, *_args, **_kwargs):
            a, v = sess.run([a0, v0], {X:ob})
            return a, v, [] #dummy state

        def value(ob, *_args, **_kwargs):
            return sess.run(v0, {X:ob})

        self.X = X
        self.pi = pi
        self.vf = vf
        self.step = step
        self.value = value


class GaussianMlpPolicy(object):
    def __init__(self, ob_dim, ac_dim):
        # Here we'll construct a bunch of expressions, which will be used in two places:
        # (1) When sampling actions
        # (2) When computing loss functions, for the policy update
        # Variables specific to (1) have the word "sampled" in them,
        # whereas variables specific to (2) have the word "old" in them
        ob_no = tf.placeholder(tf.float32, shape=[None, ob_dim*2], name="ob") # batch of observations
        oldac_na = tf.placeholder(tf.float32, shape=[None, ac_dim], name="ac") # batch of actions previous actions
        oldac_dist = tf.placeholder(tf.float32, shape=[None, ac_dim*2], name="oldac_dist") # batch of actions previous action distributions
        adv_n = tf.placeholder(tf.float32, shape=[None], name="adv") # advantage function estimate
        wd_dict = {}
        h1 = tf.nn.tanh(dense(ob_no, 64, "h1", weight_init=U.normc_initializer(1.0), bias_init=0.0, weight_loss_dict=wd_dict))
        h2 = tf.nn.tanh(dense(h1, 64, "h2", weight_init=U.normc_initializer(1.0), bias_init=0.0, weight_loss_dict=wd_dict))
        mean_na = dense(h2, ac_dim, "mean", weight_init=U.normc_initializer(0.1), bias_init=0.0, weight_loss_dict=wd_dict) # Mean control output
        self.wd_dict = wd_dict
        self.logstd_1a = logstd_1a = tf.get_variable("logstd", [ac_dim], tf.float32, tf.zeros_initializer()) # Variance on outputs
        logstd_1a = tf.expand_dims(logstd_1a, 0)
        std_1a = tf.exp(logstd_1a)
        std_na = tf.tile(std_1a, [tf.shape(mean_na)[0], 1])
        ac_dist = tf.concat([tf.reshape(mean_na, [-1, ac_dim]), tf.reshape(std_na, [-1, ac_dim])], 1)
        sampled_ac_na = tf.random_normal(tf.shape(ac_dist[:,ac_dim:])) * ac_dist[:,ac_dim:] + ac_dist[:,:ac_dim] # This is the sampled action we'll perform.
        logprobsampled_n = - U.sum(tf.log(ac_dist[:,ac_dim:]), axis=1) - 0.5 * tf.log(2.0*np.pi)*ac_dim - 0.5 * U.sum(tf.square(ac_dist[:,:ac_dim] - sampled_ac_na) / (tf.square(ac_dist[:,ac_dim:])), axis=1) # Logprob of sampled action
        logprob_n = - U.sum(tf.log(ac_dist[:,ac_dim:]), axis=1) - 0.5 * tf.log(2.0*np.pi)*ac_dim - 0.5 * U.sum(tf.square(ac_dist[:,:ac_dim] - oldac_na) / (tf.square(ac_dist[:,ac_dim:])), axis=1) # Logprob of previous actions under CURRENT policy (whereas oldlogprob_n is under OLD policy)
        kl = U.mean(kl_div(oldac_dist, ac_dist, ac_dim))
        #kl = .5 * U.mean(tf.square(logprob_n - oldlogprob_n)) # Approximation of KL divergence between old policy used to generate actions, and new policy used to compute logprob_n
        surr = - U.mean(adv_n * logprob_n) # Loss function that we'll differentiate to get the policy gradient
        surr_sampled = - U.mean(logprob_n) # Sampled loss of the policy
        self._act = U.function([ob_no], [sampled_ac_na, ac_dist, logprobsampled_n]) # Generate a new action and its logprob
        #self.compute_kl = U.function([ob_no, oldac_na, oldlogprob_n], kl) # Compute (approximate) KL divergence between old policy and new policy
        self.compute_kl = U.function([ob_no, oldac_dist], kl)
        self.update_info = ((ob_no, oldac_na, adv_n), surr, surr_sampled) # Input and output variables needed for computing loss
        U.initialize() # Initialize uninitialized TF variables

    def act(self, ob):
        ac, ac_dist, logp = self._act(ob[None])
        return ac[0], ac_dist[0], logp[0]
