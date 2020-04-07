"""
Active learning on digit recognition and metrics
================================================

In this example, we run an experiment on real data and show how active
learning can be monitored, given that in real life there is no access
to the ground truth of the test set. Based on these metrics, we
identify two phases during our active learning experiment and we define
a custom query sampler that takes advantage of this.
"""


##############################################################################
# Those are the necessary imports and initializations

from matplotlib import pyplot as plt
import numpy as np

from sklearn.datasets import load_digits
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import pairwise_distances

from cardinal.uncertainty import ConfidenceSampler
from cardinal.clustering import KMeansSampler
from cardinal.random import RandomSampler
from cardinal.plotting import plot_confidence_interval
from cardinal.base import BaseQuerySampler

np.random.seed(7)

##############################################################################
# Parameters of our experiment:
# * _batch_size_ is the number of samples that will be annotated and added to
#   the training set at each iteration
# * _n_iter_ is the number of iterations in our simulation
#
# We use the digits dataset and a RandomForestClassifier.

batch_size = 20
n_iter = 20

X, y = load_digits(return_X_y=True)
X /= 255.

model = RandomForestClassifier()


##############################################################################
# Experimental metrics
# --------------------
#
# We define a first metric based on contradictions. It has been observed that
# the number of samples on which the model changes his prediction from one
# iteration to the other is correlated to the improvement of accuracy. We
# want to verify this. Since the number of label prediction changes can be
# coarse, we use the absolute difference in prediction probabilities.

def compute_contradiction(previous_proba, current_proba):
    return np.abs(current_proba - previous_proba).mean()


##############################################################################
# We define a second metric based on the distance between already labeled
# samples and our test set. The goal of this metric is measure how well our
# test set has been explored by our query sampling method so far. We expect
# uncertainty sampling to explore the sample space located *nearby* the
# decision boundary so to have poor exploration.

def compute_exploration(X_selected, X_test):
    return pairwise_distances(X_selected, X_test).mean()

##############################################################################
# A new custom sampler
# --------------------
#
# Let us foresee the future a little bit and imagine an ideal query sampler.
# Uncertainty sampling is certainly an appealing method but in a previous
# example we have shown that it lacks exploration and can stay stuck in a
# local minimum for a while. On the other hand, K-Means sampling explore the
# space well but will probably fail at fine tuning our prediction model. In
# that context, it seems reasonable to say that we want to explore the sample
# space first, say by using a KMeansSampler, and at some point shift to
# an exploitation mode where we fine tune our model using UncertaintySampker.
# We define an Adaptive Sampler that does exactly this.
#
# As a heuristic, let us say that we keep exploring until we have explored 10%
# of our test set.


class AdaptiveQuerySampler(BaseQuerySampler):
    def __init__(self, exploration_sampler, exploitation_sampler):
        self.exploration_sampler = exploration_sampler
        self.exploitation_sampler = exploitation_sampler
        self._X_train_size = None
    
    def fit(self, X_train, y_train):
        self._X_train_size = X_train.shape[0]
        self.exploration_sampler.fit(X_train, y_train)
        self.exploitation_sampler.fit(X_train, y_train)
        return self
    
    def select_samples(self, X):
        if self._X_train_size <= 50:
            return self.exploration_sampler.select_samples(X)
        else:
            return self.exploitation_sampler.select_samples(X)


adaptive_sampler = AdaptiveQuerySampler(
    KMeansSampler(batch_size),  # Exploration
    ConfidenceSampler(model, batch_size)  # Exploitation
)

##############################################################################
# Core active learning experiment
# -------------------------------
#
# We now perform our experiment. We compare our adaptive model to random,
# pure exploration, and pure exploitation. We also monitor the metrics that
# we defined before.

samplers = [
    ('Adaptive', adaptive_sampler),
    ('Lowest confidence', ConfidenceSampler(model, batch_size)),
    ('KMeans', KMeansSampler(batch_size)),
    ('Random', RandomSampler(batch_size)),
]

figure_accuracies = plt.figure().number
figure_contradictions = plt.figure().number
figure_explorations = plt.figure().number

for i, (sampler_name, sampler) in enumerate(samplers):
    
    all_accuracies = []
    all_contradictions = []
    all_explorations = []

    for k in range(10):
        X_train, X_test, y_train, y_test = \
            train_test_split(X, y, test_size=500, random_state=k)

        accuracies = []
        contradictions = []
        explorations = []

        previous_proba = None

        # For simplicity, we start with one sample of each class
        _, selected = np.unique(y_train, return_index=True)

        # We use binary masks to simplify some operations
        mask = np.zeros(X_train.shape[0], dtype=bool)
        indices = np.arange(X_train.shape[0])
        mask[selected] = True

        # The classic active learning loop
        for j in range(n_iter):
            model.fit(X_train[mask], y_train[mask])

            # Record metrics
            accuracies.append(model.score(X_test, y_test))
            explorations.append(compute_exploration(X_train[mask], X_test))

            # Contradictions depend on the previous iteration
            current_proba = model.predict_proba(X_test)
            if previous_proba is not None:
                contradictions.append(compute_contradiction(
                    previous_proba, current_proba))
            previous_proba = current_proba

            sampler.fit(X_train[mask], y_train[mask])
            selected = sampler.select_samples(X_train[~mask])
            mask[indices[~mask][selected]] = True

        all_accuracies.append(accuracies)
        all_explorations.append(explorations)
        all_contradictions.append(contradictions)
    
    x_data = np.arange(10, batch_size * (n_iter - 1) + 11, batch_size)

    plt.figure(figure_accuracies)
    plot_confidence_interval(x_data, all_accuracies, label=sampler_name)

    plt.figure(figure_contradictions)
    plot_confidence_interval(x_data[1:], all_contradictions,
                             label=sampler_name)

    plt.figure(figure_explorations)
    plot_confidence_interval(x_data, all_explorations, label=sampler_name)

plt.figure(figure_accuracies)
plt.xlabel('Labeled samples')
plt.ylabel('Accuracy')
plt.gca().axvline(50, color='r')
plt.legend()
plt.tight_layout()

plt.figure(figure_contradictions)
plt.xlabel('Labeled samples')
plt.ylabel('Contradictions')
plt.gca().axvline(50, color='r')
plt.legend()
plt.tight_layout()

plt.figure(figure_explorations)
plt.xlabel('Labeled samples')
plt.ylabel('Exploration score')
plt.gca().axvline(50, color='r')
plt.legend()
plt.tight_layout()

plt.show()

##############################################################################
# Discussion
# ----------
#
# Accuracies
# ^^^^^^^^^^
#
# In all our figures, the vertical red line indicates when the adaptive
# method switches from exploration to exploitation.
#
# We first look at our accuracy. As expected, KMeansSampler, our exploration
# method is the best at the beginning but becomes as performant as random
# with time. Uncertainty sampling also behaves as expected by starting bad and
# then becoming the best method.
#
# Our Adaptive sampler combines the performance of both approaches to have the
# best performance!
#
# Contradictions
# ^^^^^^^^^^^^^^
#
# Now, we want to know if contradictions are a good proxy for performance. We
# observe with bare eyes that it indeed looks related to the speed (gradient)
# of the accuracy curves. In the end of the experiment in particular,
# uncertainty and adaptive the ones increasing faster and their contradictions
# are also the highest.
#
# Exploration scores
# ^^^^^^^^^^^^^^^^^^
#
# The exploration curve also displays interesting trends. Since those are
# distance, a good exploration method will have a low score. As expected,
# exploration-based methods have the lowest scores. In particular,
# KMeansSampler starts by decreasing and then goes up. At the same time, its
# performance starts stalling. This shift happens incidentally at the same
# time as our adaptive method shifts its method. This is obviously not random!
# This exploration metric can be used to decide when to change method.