#!/usr/bin/python
# -*- coding: utf-8 -*-
from sqlalchemy import (create_engine, inspect, exists, Column, Unicode, String,
                        Integer, Boolean, DateTime, Enum,
                        MetaData, Numeric, Table, Text)
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.engine.url import URL
from sqlalchemy import func, and_

import traceback
import random, sys
import os
from datetime import datetime
import warnings
import pdb

from atm.constants import *
from atm.utilities import object_to_base_64, base_64_to_object


class LearnerStatus:
    STARTED = 'started'
    ERRORED = 'errored'
    COMPLETE = 'complete'

class RunStatus:
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETE = 'complete'

#   ('code', 'Name', probability)
ALGORITHM_ROWS = [
	dict(id=1, code='svm', name='Support Vector Machine', probability=True),
	dict(id=2, code='et', name='Extra Trees', probability=True),
	dict(id=3, code='pa', name='Passive Aggressive', probability=False),
	dict(id=4, code='sgd', name='Stochastic Gradient Descent', probability=True),
	dict(id=5, code='rf', name='Random Forest', probability=True),
	dict(id=6, code='mnb', name='Multinomial Naive Bayes', probability=True),
	dict(id=7, code='bnb', name='Bernoulii Naive Bayes', probability=True),
	dict(id=8, code='dbn', name='Deef Belief Network', probability=False),
	dict(id=9, code='logreg', name='Logistic Regression', probability=True),
	dict(id=10, code='gnb', name='Gaussian Naive Bayes', probability=True),
	dict(id=11, code='dt', name='Decision Tree', probability=True),
	dict(id=12, code='knn', name='K Nearest Neighbors', probability=True),
	dict(id=13, code='mlp', name='Multi-Layer Perceptron', probability=True),
	dict(id=14, code='gp', name='Gaussian Process', probability=True),
]


def try_with_session(default=lambda: None, commit=False):
    """
    Decorator for instance methods on Database that need a sqlalchemy session.

    This wrapping function creates a new session with the Database's engine and
    passes it to the instance method to use. Everything is inside a try-catch
    statement, so if something goes wrong, this prints a nice error string and
    fails gracefully.

    In case of an error, the function passed to this decorator as `default` is
    called (without arguments) to generate a response. This needs to be a
    function instead of just a static argument to avoid issues with leaving
    empty lists ([]) in method signatures.
    """
    def wrap(func):
        def call(db, *args, **kwargs):
            session = db.get_session()
            try:
                result = func(db, session, *args, **kwargs)
                if commit:
                    session.commit()
            except Exception:
                if commit:
                    session.rollback()
                result = default()
                argstr = ', '.join([str(a) for a in args])
                kwargstr = ', '.join(['%s=%s' % kv for kv in kwargs.items()])
                print "Error in %s(%s, %s):" % (func.__name__, argstr, kwargstr)
                print traceback.format_exc()
            finally:
                session.close()

            return result
        return call
    return wrap


class Database(object):
    def __init__(self, dialect, database, username=None, password=None,
                 host=None, port=None, query=None):
        """
        Accepts configuration for a database connection, and defines SQLAlchemy
        ORM objects for all the tables in the database.
        """
        db_url = URL(drivername=dialect, database=database, username=username,
                     password=password, host=host, port=port, query=query)
        self.engine = create_engine(db_url)

        self.get_session = sessionmaker(bind=self.engine,
                                        expire_on_commit=False)
        self.define_tables()
        self.create_algorithms()

    def define_tables(self):
        metadata = MetaData(bind=self.engine)
        Base = declarative_base()

        class Algorithm(Base):
            __tablename__ = 'algorithms'

            id = Column(Integer, primary_key=True, autoincrement=True)
            code = Column(String(15), nullable=False)
            name = Column(String(30), nullable=False)
            probability = Column(Boolean)

            def __repr__(self):
                return "<%s>" % self.name

        self.Algorithm = Algorithm

        class Dataset(Base):
            __tablename__ = 'datasets'

            id = Column(Integer, primary_key=True, autoincrement=True)

            name = Column(String(100), nullable=False)
            description = Column(String(1000))
            train_path = Column(String(200), nullable=False)
            test_path = Column(String(200))
            wrapper64 = Column(String(200), nullable=False)

            label_column = Column(Integer, nullable=False)
            n_examples = Column(Integer, nullable=False)
            k_classes = Column(Integer, nullable=False)
            d_features = Column(Integer, nullable=False)
            majority = Column(Numeric(precision=10, scale=9), nullable=False)
            size_kb = Column(Integer, nullable=False)

            @property
            def wrapper(self):
                return base_64_to_object(self.wrapper64)

            @wrapper.setter
            def wrapper(self, value):
                self.wrapper64 = object_to_base_64(value)

            def __repr__(self):
                base = "<%s: %s, %d classes, %d features, %d examples>"
                return base % (self.name, self.description, self.k_classes,
                               self.d_features, self.n_examples)

        self.Dataset = Dataset

        class Datarun(Base):
            __tablename__ = 'dataruns'

            id = Column(Integer, primary_key=True, autoincrement=True)
            dataset_id = Column(Integer)

            description = Column(String(200), nullable=False)
            priority = Column(Integer)

            selector = Column(Enum(*SELECTORS), nullable=False)
            k_window = Column(Integer)
            tuner = Column(Enum(*TUNERS), nullable=False)
            gridding = Column(Integer, nullable=False)
            r_min = Column(Integer)

            budget_type = Column(Enum(*BUDGET_TYPES))
            budget = Column(Integer)
            deadline = Column(DateTime)

            metric = Column(Enum(*METRICS))
            score_target = Column(Enum(*[s + '_judgment_metric' for s in
                                         SCORE_TARGETS]))

            started = Column(DateTime)
            completed = Column(DateTime)
            status = Column(Enum(*DATARUN_STATUS), default=RunStatus.PENDING)

            def __repr__(self):
                base = "<%d: %s, budget: %s (%s), status: %s>"
                return base % (self.id, self.description, self.budget_type,
                               self.budget, self.status)

        self.Datarun = Datarun

        class FrozenSet(Base):
            __tablename__ = 'frozen_sets'

            id = Column(Integer, primary_key=True, autoincrement=True)
            datarun_id = Column(Integer)
            algorithm = Column(String(15), nullable=False)

            trained = Column(Integer, default=0)
            optimizables64 = Column(Text)
            constants64 = Column(Text)
            frozens64 = Column(Text)
            frozen_hash = Column(String(32))
            is_gridding_done = Column(Boolean, default=False)

            @property
            def optimizables(self):
                return base_64_to_object(self.optimizables64)

            @optimizables.setter
            def optimizables(self, value):
                self.optimizables64 = object_to_base_64(value)

            @property
            def frozens(self):
                return base_64_to_object(self.frozens64)

            @frozens.setter
            def frozens(self, value):
                self.frozens64 = object_to_base_64(value)

            @property
            def constants(self):
                return base_64_to_object(self.constants64)

            @constants.setter
            def constants(self, value):
                self.constants64 = object_to_base_64(value)

            def __repr__(self):
                return "<%s: %s>" % (self.algorithm, self.frozens)

        self.FrozenSet = FrozenSet

        class Learner(Base):
            __tablename__ = 'learners'

            id = Column(Integer, primary_key=True, autoincrement=True)
            frozen_set_id = Column(Integer)
            datarun_id = Column(Integer)

            model_path = Column(String(300))
            metric_path = Column(String(300))
            host = Column(String(50))
            params64 = Column(Text, nullable=False)
            trainable_params64 = Column(Text)
            dimensions = Column(Integer)

            cv_judgment_metric = Column(Numeric(precision=20, scale=10))
            cv_judgment_metric_stdev = Column(Numeric(precision=20, scale=10))
            test_judgment_metric = Column(Numeric(precision=20, scale=10))

            started = Column(DateTime)
            completed = Column(DateTime)
            status = Column(Enum(*LEARNER_STATUS), nullable=False)
            error_msg = Column(Text)

            @property
            def params(self):
                return base_64_to_object(self.params64)

            @params.setter
            def params(self, value):
                self.params64 = object_to_base_64(value)

            @property
            def trainable_params(self):
                return base_64_to_object(self.trainable_params64)

            @trainable_params.setter
            def trainable_params(self, value):
                self.trainable_params64 = object_to_base_64(value)

            def __repr__(self):
                return "<%s>" % self.params

        self.Learner = Learner

        Base.metadata.create_all(bind=self.engine)

    @try_with_session()
    def create_algorithms(self, session):
        """ Enter all the default algorithms into the database """
        for r in ALGORITHM_ROWS:
            if not session.query(self.Dataset).get(r['id']):
                del r['id']
                alg = self.Algorithm(**r)
                session.add(alg)
        session.commit()

    @try_with_session()
    def GetDatarun(self, session, datarun_id=None, ignore_completed=True,
                   ignore_grid_complete=False, choose_randomly=True):
        """
        Return a single datarun.
        Args:
            datarun_id: return the datarun with this id
            ignore_completed: if True, ignore completed dataruns
            ignore_grid_complete: if True, ignore dataruns with is_gridding_done
            choose_randomly: if True, choose one of the possible dataruns to
                return randomly. If False, return the first datarun present in
                the database (likely lowest id).
        """
        query = session.query(self.Datarun)
        if ignore_completed:
            query = query.filter(self.Datarun.completed == None)
        if ignore_grid_complete:
            query = query.filter(self.Datarun.is_gridding_done == 0)
        if datarun_id:
            query = query.filter(self.Datarun.id == datarun_id)

        dataruns = query.all()

        if not dataruns:
            return None

        # select only those with max priority
        max_priority = max([r.priority for r in dataruns])
        candidates = [r for r in dataruns if r.priority == max_priority]

        # choose a random candidate if necessary
        if choose_randomly:
            return candidates[random.randint(0, len(candidates) - 1)]
        return candidates[0]

    @try_with_session()
    def GetDataset(self, session, dataset_id):
        """ Returns a specific dataset. """
        return session.query(self.Dataset).get(dataset_id)

    @try_with_session(default=lambda: True)
    def IsGriddingDoneForDatarun(self, session, datarun_id,
                                 errors_to_exclude=0):
        """
        Check whether gridding is done for the entire datarun.
        errors_to_exclude = 0 indicates we don't care about errors.
        """
        is_done = True
        frozen_sets = session.query(self.FrozenSet)\
            .filter(self.FrozenSet.datarun_id == datarun_id).all()

        for frozen_set in frozen_sets:
            if not frozen_set.is_gridding_done:
                num_errors = self.GetNumberOfFrozenSetErrors(frozen_set.id)
                if errors_to_exclude == 0 or num_errors < errors_to_exclude:
                    is_done = False

        return is_done

    @try_with_session(default=list)
    def GetIncompleteFrozenSets(self, session, datarun_id,
                                 errors_to_exclude=0):
        """
        Returns all the incomplete frozen sets in a given datarun by id.
        """
        frozen_sets = session.query(self.FrozenSet)\
            .filter(and_(self.FrozenSet.datarun_id == datarun_id,
                         self.FrozenSet.is_gridding_done == 0)).all()

        if not errors_to_exclude:
            return frozen_sets

        old_list = frozen_sets
        frozen_sets = []

        for frozen_set in old_list:
            if (self.GetNumberOfFrozenSetErrors(frozen_set.id) <
                    errors_to_exclude):
                frozen_sets.append(frozen_set)

        return frozen_sets

    @try_with_session()
    def GetFrozenSet(self, session, frozen_set_id):
        """ Returns a specific learner.  """
        return session.query(self.FrozenSet).get(frozen_set_id)

    @try_with_session(default=int)
    def GetNumberOfFrozenSetErrors(self, session, frozen_set_id):
        learners = session.query(self.Learner)\
            .filter(and_(self.Learner.frozen_set_id == frozen_set_id,
                         self.Learner.status == LearnerStatus.ERRORED)).all()
        return len(learners)

    @try_with_session(default=list)
    def GetLearnersInFrozen(self, session, frozen_set_id):
        """ Returns all learners in a frozen set. """
        return session.query(self.Learner)\
            .filter(self.Learner.frozen_set_id == frozen_set_id).all()

    @try_with_session(default=list)
    def GetLearners(self, session, datarun_id):
        """ Returns all learners in a datarun.  """
        return session.query(self.Learner)\
            .filter(self.Learner.datarun_id == datarun_id)\
            .order_by(self.Learner.started).all()

    @try_with_session(default=list)
    def GetCompleteLearners(self, session, datarun_id):
        """ Returns all complete learners in a datarun.  """
        return session.query(self.Learner)\
            .filter(self.Learner.datarun_id == datarun_id)\
            .filter(self.Learner.status == LearnerStatus.COMPLETE)\
            .order_by(self.Learner.started).all()

    @try_with_session()
    def GetLearner(self, session, learner_id):
        """ Returns a specific learner.  """
        return session.query(self.Learner).get(learner_id)

    @try_with_session()
    def GetMaximumY(self, session, datarun_id, score_target):
        """ Returns the maximum value of a numeric column by name, or None. """
        result = session.query(func.max(getattr(self.Learner, score_target)))\
            .filter(self.Learner.datarun_id == datarun_id).one()[0]
        if result:
            return float(result)
        return None

    @try_with_session(default=lambda: (0, 0))
    def get_best_so_far(self, session, datarun_id, score_target):
        """
        Sort of like GetMaximumY, but retuns the score with the highest lower
        error bound. In other words, what is the highest value of (score.mean -
        2 * score.std) for any learner?
        """
        maximum = 0
        best_val, best_err = 0, 0

        if score_target == 'cv_judgment_metric':
            result = session.query(self.Learner.cv_judgment_metric,
                                   self.Learner.cv_judgment_metric_stdev)\
                            .filter(self.Learner.datarun_id == datarun_id)\
                            .filter(self.Learner.status == LearnerStatus.COMPLETE)\
                            .all()
            for val, std in result:
                if val is None or std is None:
                    continue
                if val - 2 * std > maximum:
                    best_val, best_err = float(val), 2 * float(std)
                    maximum = float(val - 2 * std)

        elif score_target == 'test_judgment_metric':
            result = session.query(func.max(self.Learner.test_judgment_metric))\
                            .filter(self.Learner.datarun_id == datarun_id)\
                            .one()[0]
            if result is not None and result > maximum:
                best_val = float(result)
                maximum = best_val

        return best_val, best_err

    @try_with_session(commit=True)
    def MarkFrozenSetGriddingDone(self, session, frozen_set_id):
        frozen_set = session.query(self.FrozenSet)\
            .filter(self.FrozenSet.id == frozen_set_id).one()
        frozen_set.is_gridding_done = 1

    @try_with_session(commit=True)
    def MarkDatarunGriddingDone(self, session, datarun_id):
        datarun = session.query(self.Datarun)\
            .filter(self.Datarun.id == datarun_id).one()
        datarun.is_gridding_done = 1

    @try_with_session(commit=True)
    def MarkDatarunDone(self, session, datarun_id):
        """ Sets the completed field of the Datarun to the current datetime. """
        datarun = session.query(self.Datarun)\
            .filter(self.Datarun.id == datarun_id).one()
        datarun.completed = datetime.now()