#!/usr/bin/python3
"""kleros_db
This module it's used to define all the tables and objects of the database.
In addition different methods are created to return the information from the
datbase.
Some functions are not exposed in the website or api.
"""

import statistics
from copy import deepcopy
from datetime import datetime, timedelta
import logging

from sqlalchemy.sql.expression import func

from app.modules import db
from .etherscan import Etherscan

logger = logging.getLogger(__name__)


class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    option = db.Column(db.String(50))
    value = db.Column(db.String(50))

    @classmethod
    def get(cls, db_key):
        query = cls.query.filter(cls.option == db_key).first()
        if query is None:
            return None
        return query.value

    @classmethod
    def set(cls, db_key, db_val):
        query = cls.query.filter(cls.option == db_key)
        for item in query:
            db.session.delete(item)
        new_option = cls(option=db_key, value=db_val)
        db.session.add(new_option)
        db.session.commit()


class Court(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    address = db.Column(db.String(50))
    parent = db.Column(db.Integer, db.ForeignKey("court.id"), nullable=True)
    minStake = db.Column(db.Float)
    feeForJuror = db.Column(db.Float)
    voteStake = db.Column(db.Integer)
    meanStaked = db.Column(db.Float)
    maxStaked = db.Column(db.Float)
    totalStaked = db.Column(db.Float)
    activeJurors = db.Column(db.Integer)
    disputesLast30days = db.Column(db.Integer)
    minStakeUSD = db.Column(db.Float)

    def disputes(self, days=None):
        """
        Return the disputes in the previous days. If days is None, return all
        the disputes in that Court

        Parameters
        ----------
        days : int, optional
            Number of days to count the disputes backwards.
            The default is None.

        Returns
        -------
        List
            List of all the Disputes

        """
        if days:
            filter_after = (datetime.now() - timedelta(days=days)).replace(hour=0, minute=0, second=0)
            return Dispute.query \
                .filter(Dispute.subcourtID == self.id, Dispute.timestamp >= filter_after) \
                .order_by(Dispute.id.desc()).all()
        else:
            return Dispute.query.filter(Dispute.subcourtID == self.id).order_by(Dispute.id.desc()).all()

    def disputes_paginated(self, page=0, per_page=10):
        """
        Return the disputes of the court, paginated

        Parameters
        ----------
        page : int, optional
            Current page, by default is 0
        per_page : int, optional
            Amount of disputes per page. By default is 10

        Returns
        -------
        List
            List of all the Disputes

        """
        return Dispute.query.filter(Dispute.subcourtID == self.id).order_by(Dispute.id.desc()).paginate(page,
                                                                                                        per_page,
                                                                                                        error_out=False)

    @property
    def openCases(self):
        return Dispute.query.filter(Dispute.ruled == 0).filter(Dispute.subcourtID == self.id).count()

    @property
    def ruledCases(self):
        return Dispute.query.filter(Dispute.ruled == 1).filter(Dispute.subcourtID == self.id).count()

    def get_recursive_childs(self, node=0):
        query = f"""
                WITH RECURSIVE cte_court (id, name, parent) AS (
                    SELECT e.id, e.name, e.parent
                    FROM court e
                    WHERE e.id = {node}

                    UNION ALL

                    SELECT e.id, e.name, e.parent
                    FROM court e
                    JOIN cte_court c ON c.id = e.parent
                )

                SELECT * FROM cte_court ORDER BY cte_court.id;
        """
        return [{'id': child[0], 'name': child[1]} for child in db.session.execute(query)]

    @property
    def children_ids(self):
        return [child.id for child in Court.query.filter(Court.parent == self.id)]

    @property
    def children_names(self):
        return [child.name for child in Court.query.filter(Court.parent == self.id)]

    @property
    def childrens(self):
        return [child for child in Court.query.filter(Court.parent == self.id)]

    @property
    def fees_paid(self):
        disputes = Dispute.query.filter_by(subcourtID=self.id)
        eth_fees_paid = 0
        pnk_distributed = 0
        for dispute in disputes:
            rounds = dispute.rounds()
            for r in rounds:
                eth_fees_paid += r.total_fees_for_jurors
                pnk_distributed += r.penalties_in_each_round
        return {'eth': eth_fees_paid,
                'pnk': pnk_distributed}

    @staticmethod
    def getAllCourtChilds(courtID):
        childs = set(Court(id=courtID).children_ids)
        allChilds = []
        while childs:
            child = childs.pop()
            allChilds.append(child)
            childs.update(Court(id=child).children_ids)
        return allChilds

    @staticmethod
    def getParent(courtID):
        return Court.query.filter_by(id=courtID).first().parent

    @property
    def ncourts(self):
        return Court.query.count()

    @property
    def jurors(self):
        courts_childs = Court.getAllCourtChilds(self.id)
        courts_childs.append(self.id)
        if len(courts_childs) > 1:
            courts_id = tuple(courts_childs)
        else:
            courts_id = f'({courts_childs[0]})'
        query = f"""
            SELECT address, SUM(setStake) as staked
            FROM (
                SELECT address, setStake
                FROM juror_stake
                WHERE id IN (
                    SELECT MAX(id)
                    FROM juror_stake
                    WHERE subcourtID in {courts_id}
                    GROUP BY address, subcourtID
                    )
            ) as Jurors
            WHERE setStake > 0
            GROUP BY address
            ORDER BY setStake DESC
            """
        execute = db.session.execute(query).fetchall()
        jurors = {}
        for juror in execute:
            jurors[juror[0]] = juror[1]
        return jurors

    @property
    def map_name(self):
        if self.name:
            return self.name
        else:
            return self.query.filter(Court.id == self.id).first().name

    def yes_no_coherency(self):
        coherency = {'Refuse': 0, 'Yes': 0, 'No': 0}
        incoherents = {'Refuse': 0, 'Yes': 0, 'No': 0, 'Pending': 0}
        for d in self.disputes():
            data = d.yes_no_coherency()
            if data:
                for key, value in data['coherents'].items():
                    coherency[key] += value
                for key, value in data['incoherents'].items():
                    incoherents[key] += value
        totals = {'coherents': sum([value for value in coherency.values()])}
        totals['incoherents'] = sum([value for value in incoherents.values()])
        totals['percentage_coherents'] = totals['coherents'] / (totals['coherents'] + totals['incoherents'])
        if all([value == 0 for value in coherency.values()]):
            return None
        else:
            return {'coherents': coherency,
                    'incoherents': incoherents,
                    'totals': totals}

    def juror_stats(self):
        jurors = self.jurors
        try:
            court_mean = statistics.mean(jurors.values())
        except Exception as e:
            court_mean = 0
            logger.info(f"Could not get the mean value of the court {self.id}")
            logger.error(e)
        try:
            court_median = statistics.median(jurors.values())
        except Exception as e:
            court_median = 0
            logger.info(f"Could not get the median value of the court {self.id}")
            logger.error(e)
        try:
            court_max = max(jurors.values())
        except Exception as e:
            court_max = 0
            logger.info(f"Could not get the max value of the court {self.id}")
            logger.error(e)

        return {
            'length': len(jurors.values()),
            'mean': court_mean,
            'median': court_median,
            'max': court_max,
            'total': sum(jurors.values())
        }

    @staticmethod
    def updateStatsAllCourts():
        courts = db.session.query(Court.id).all()
        pnkPrice = float(Config.get('PNKprice'))
        for court in courts:
            c = Court.query.filter_by(id=court.id).first()
            stats = c.juror_stats()
            c.meanStaked = int(stats['mean'])
            c.maxStaked = int(stats['max'])
            c.totalStaked = int(stats['total'])
            c.activeJurors = stats['length']
            c.disputesLast30days = len(c.disputes(30))
            c.minStakeUSD = c.minStake*pnkPrice
            db.session.add(c)
        db.session.commit()
        logger.debug("Stats of Courts updated")


class Dispute(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number_of_choices = db.Column(db.Integer)
    subcourtID = db.Column(db.Integer, db.ForeignKey("court.id"), nullable=False)
    status = db.Column(db.Integer)
    arbitrated = db.Column(db.String(50))
    current_ruling = db.Column(db.Integer)
    period = db.Column(db.Integer)
    last_period_change = db.Column(db.DateTime)
    ruled = db.Column(db.Boolean)
    creator = db.Column(db.String(50))
    txid = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime)
    blocknumber = db.Column(db.Integer)

    def __eq__(self, other):
        classes_match = isinstance(other, self.__class__)
        a, b = deepcopy(self.__dict__), deepcopy(other.__dict__)
        # compare based on equality our attributes, ignoring SQLAlchemy internal stuff
        a.pop('_sa_instance_state', None)
        b.pop('_sa_instance_state', None)
        attrs_match = (a == b)
        return classes_match and attrs_match

    def __str__(self):
        return f'Dispute(id={self.id}, court={self.subcourtID}, period={self.period}, ruled={self.ruled}, current_ruling={self.current_ruling})'

    def __ne__(self, other):
        return not self.__eq__(other)

    def rounds(self):
        return Round.query.filter_by(disputeID=self.id).all()

    @property
    def court(self):
        return Court.query.get(self.subcourtID)

    @property
    def period_name(self):
        period_name = {
            0: "Evidence",
            1: "Commit",
            2: "Vote",
            3: "Appeal",
            4: "Execution",
        }
        return period_name[self.period]

    @property
    def winner_choice_str(self):
        choice_name = {
            0: 'Refuse to Arbitrate',
            1: 'Yes',
            2: 'No',
            3: 'Tie',
            4: 'Not Ruled yet'}
        if self.winning_choice is not None:
            return choice_name[self.winning_choice]
        else:
            return choice_name[4]

    def delete_recursive(self):
        rounds = Round.query.filter(Round.disputeID == self.id)
        for r in rounds:
            r.delete_recursive()
        logger.info("Deleting Dispute %s" % self.id)
        db.session.delete(self)
        db.session.commit()

    @property
    def openCases(self):
        return self.query.filter(Dispute.ruled == 0).count()

    @property
    def ruledCases(self):
        return self.query.filter(Dispute.ruled == 1).count()

    @staticmethod
    def mostActiveCourt(days=7):
        """
        Most active cour in the last days

        Parameters
        ----------
        days : int, optional
            DESCRIPTION. Last Days to filter. The default is 7.

        Returns
        -------
        Court object with the most active Court in the last days.

        """
        filter_after = datetime.today() - timedelta(days=days)

        disputes = Dispute.query.filter(Dispute.timestamp >= filter_after).all()
        counts = {}
        for dispute in disputes:
            try:
                counts[dispute.subcourtID] += 1
            except KeyError:
                counts[dispute.subcourtID] = 1
        try:
            mostActive = max(counts, key=counts.get)
            return {mostActive: counts[mostActive]}
        except Exception:
            return None

    @staticmethod
    def timeEvolution():
        """
        Return the timestamp and Dispute amounts
        """
        disputes = db.session.query(Dispute.id, Dispute.timestamp).all()
        allDisputes = []
        for dispute in disputes:
            allDisputes.append({'timestamp': dispute.timestamp,
                                'id': dispute.id})
        return allDisputes

    @staticmethod
    def disputesCountByCourt():
        data = Dispute.query.with_entities(Dispute.subcourtID, func.count(Dispute.id)).\
            group_by(Dispute.subcourtID).all()
        result = {}
        for item in data:
            result[Court(id=item[0]).map_name] = item[1]
        return result

    @staticmethod
    def disputesCountByArbitrated():
        data = Dispute.query.with_entities(Dispute.arbitrated, func.count(Dispute.id)).\
            group_by(Dispute.arbitrated).all()
        result = {}
        for item in data:
            name = ContractMapper.searchName(item[0])
            if name in list(result.keys()):
                result[name] += item[1]
            else:
                result[name] = item[1]
        return result

    @staticmethod
    def disputesByArbitrated(address):
        disputes = Dispute.query.filter(func.lower(Dispute.arbitrated) == address.lower()).order_by(Dispute.id.desc()).all()
        return list(disputes)

    @staticmethod
    def disputesByCreator(address):
        disputes = Dispute.query.filter(func.lower(Dispute.creator) == address.lower()).order_by(Dispute.id.desc()).all()
        return list(disputes)

    @staticmethod
    def disputesByCreator_paginated(address, page=0, per_page=10):
        return Dispute.query.filter(func.lower(Dispute.creator) == address.lower()).order_by(Dispute.id.desc()).paginate(page,
                                                                                                        per_page,
                                                                                                        error_out=False)

    @property
    def winning_choice(self):
        max_round_id = self.rounds()[-1].id
        if Dispute.query.filter_by(id=self.id).first().ruled:
            votes_query = db.session.execute(
                "select choice,count(*) as num_votes from vote \
                where round_id = :round_id and vote=1 \
                group by choice order by num_votes desc", {'round_id': max_round_id}).fetchall()
            num_of_votes = [count[1] for count in votes_query]
            if len(num_of_votes) == 0:
                # all the votes are still pending
                return None
            if (len(num_of_votes) > 1) and (all(count == num_of_votes[0] for count in num_of_votes)):
                # it's a tie
                return 3
            else:
                return votes_query[0].items()[0][1]
        else:
            return None

    def coherency(self):
        """
        Percentage of coherent votes with the final result
        """
        if Dispute.query.filter_by(id=self.id).first().ruled:
            coherent_votes = 0
            no_coherent_votes = 0
            rounds = self.rounds()
            for r in rounds:
                for vote in r.votes():
                    if self.winning_choice != 3:
                        # if it's not a tie
                        if (vote.vote) and (vote.choice == self.winning_choice):
                            coherent_votes += 1
                        elif not vote.vote:
                            # if didn't vote, don't count it
                            # TODO! review if this is fine
                            pass
                        else:
                            no_coherent_votes += 1
                    else:

                        # if it's a tie, if voted it's coherent, if not, isn't
                        if vote.vote:
                            coherent_votes += 1
                        else:
                            no_coherent_votes += 1
            if coherent_votes + no_coherent_votes:
                return coherent_votes / (coherent_votes + no_coherent_votes)
            else:
                return None
        else:
            return None

    def yes_no_coherency(self):
        """
        Number of votes for yes or no that are coherent with the final result
        """
        coherency = {'Refuse': 0, 'Yes': 0, 'No': 0}
        incoherents = {'Refuse': 0, 'Yes': 0, 'No': 0, 'Pending': 0}
        mapper = {0: 'Refuse', 1: 'Yes', 2: 'No'}
        if Dispute.query.filter_by(id=self.id).first().ruled:
            for r in self.rounds():
                for vote in r.votes():
                    if self.winning_choice != 3:
                        # if it's not a tie
                        if (vote.vote) and (vote.choice == self.winning_choice):
                            coherency[mapper[vote.choice]] += 1
                        elif not vote.vote:
                            incoherents['Pending'] += 1
                        else:
                            incoherents[mapper[vote.choice]] += 1
                    else:
                        # if it's a tie, if voted it's coherent, if not, isn't
                        if vote.vote:
                            coherency[mapper[vote.choice]] += 1
                        else:
                            incoherents['Pending'] += 1
            return {'coherents': coherency, 'incoherents': incoherents}
        else:
            return None


class Round(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_num = db.Column(db.Integer)
    disputeID = db.Column(db.Integer, db.ForeignKey("dispute.id"), nullable=False)
    draws_in_round = db.Column(db.Integer)
    commits_in_round = db.Column(db.Integer)
    appeal_start = db.Column(db.Integer)
    appeal_end = db.Column(db.Integer)
    vote_lengths = db.Column(db.Integer)
    tokens_at_stake_per_juror = db.Column(db.Float)
    total_fees_for_jurors = db.Column(db.Float)
    votes_in_each_round = db.Column(db.Integer)
    repartitions_in_each_round = db.Column(db.Float)
    penalties_in_each_round = db.Column(db.Float)
    subcourtID = db.Column(db.Integer, db.ForeignKey("court.id"), nullable=False)

    def __str__(self):
        return f'Round(court={self.subcourtID}, dispute_id={self.disputeID}, number={self.round_num}, drawns={self.draws_in_round}, commits={self.commits_in_round})'

    def __eq__(self, other):
        classes_match = isinstance(other, self.__class__)
        a, b = deepcopy(self.__dict__), deepcopy(other.__dict__)
        # compare based on equality our attributes, ignoring SQLAlchemy internal stuff
        avoid_fields = ['_sa_instance_state', 'id', 'appeal_start', 'appeal_end',
                        'vote_lengths', 'votes_in_each_round']
        for field in avoid_fields:
            a.pop(field, None)
            b.pop(field, None)
        
        attrs_match = (a == b)
        return classes_match and attrs_match

    def __ne__(self, other):
        return not self.__eq__(other)

    def votes(self):
        return Vote.query.filter_by(round_id=self.id).order_by(Vote.account.asc()).all()
    
    def votes_drawn_order(self):
        return Vote.query.filter_by(round_id=self.id).order_by(Vote.id.asc()).all()

    def vote_count(self):
        count = {'Yes': 0, 'No': 0, 'Refuse': 0, 'Pending': 0}
        for v in self.votes():
            count[v.vote_str] += 1
        return count

    def delete_recursive(self):
        votes = Vote.query.filter(Vote.round_id == self.id)
        for v in votes:
            logger.info("Deleting Vote %s" % v.id)
            db.session.delete(v)
        db.session.commit()
        logger.info("Deleting round %s" % self.id)
        db.session.delete(self)
        db.session.commit()

    @property
    def majority_reached(self):
        votes_cast = []
        votes_cast.append(Vote.query.filter(Vote.round_id == self.id).filter(Vote.vote == 1).filter(Vote.choice==1).count())
        votes_cast.append(Vote.query.filter(Vote.round_id == self.id).filter(Vote.vote == 1).filter(Vote.choice==2).count())
        votes_cast.append(Vote.query.filter(Vote.round_id == self.id).filter(Vote.vote == 1).filter(Vote.choice==0).count())
        return any(x >= self.draws_in_round/2 for x in votes_cast)

    @property
    def winning_choice(self):
        # votes = Vote.query.filter(Vote.round_id == self.id).count()
        votes_query = db.session.execute(
            "select choice,count(*) as num_votes from vote \
            where round_id = :round_id and vote=1 \
            group by choice order by num_votes desc", {'round_id': self.id}).first()
        return(votes_query[0])


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    round_id = db.Column(db.Integer, db.ForeignKey("round.id"), nullable=False)
    account = db.Column(db.String(50))
    commit = db.Column(db.Integer)
    choice = db.Column(db.Integer)
    vote = db.Column(db.Integer)
    date = db.Column(db.DateTime)

    def __str__(self):
        return f'Vote(juror={self.account}, choice={self.choice}, vote={self.vote}, commit={self.commit})'

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            attrs_match = ((self.account.lower() == other.account.lower()) and
                           (self.commit == other.commit) and
                           (self.choice == other.choice) and
                           (self.vote == other.vote)
                           )
            return attrs_match
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @property
    def is_winner(self):
        """
        Check if the vote is winner in its round
        """
        round = Round.query.get(self.round_id)
        if not round.majority_reached:
            return False
        return self.choice == round.winning_choice

    @property
    def vote_str(self):
        map_votes = {0: 'Refuse to Arbitrate',
                     1: 'Yes',
                     2: 'No',
                     3: 'Pending'}
        try:
            if self.vote == 1:
                return map_votes[self.choice]
            else:
                return map_votes[3]
        except KeyError:
            logger.error("Key error not found when mapping the vote string")
            logger.error("The vote has the properties: ID:{}, Vote:{}, Choice{}".format(self.id, self.vote, self.choice))
            return ''


class Juror():
    def __init__(self, address):
        self.address = address.lower()

    @classmethod
    def list(cls):
        """
        List all the jurors drawn at least one time.
        """
        jurors_query = db.session.execute(
            "SELECT DISTINCT(vote.account), count(vote.id) from vote, round, dispute \
            WHERE vote.round_id = round.id \
            AND round.disputeID = dispute.id \
            GROUP BY vote.account"
        )
        jurors = []
        for jq in jurors_query:
            jurors.append({
                'address': jq[0],
                'votes': jq[1]
            })
        return jurors

    @staticmethod
    def stakedJurors():
        allStakes = db.session.execute(
            "SELECT id,address,setStake, subcourtID \
                FROM juror_stake \
                WHERE id IN ( \
                    SELECT MAX(id) \
                    FROM juror_stake \
                    GROUP BY address,subcourtID);"
        )
        stakedJurors = {}
        for stake in allStakes:
            if stake.setStake > 0:
                if stake.address.lower() not in stakedJurors.keys():
                    stakedJurors[stake.address.lower()] = [{stake.subcourtID: stake.setStake}]
                else:
                    stakedJurors[stake.address.lower()].append({stake.subcourtID: stake.setStake})

        return stakedJurors

    def votes_in_court(self, court_id):
        votes_in_court = db.session.execute(
            "SELECT count(vote.id) from vote, round, dispute \
            WHERE vote.account = :address \
            AND vote.round_id = round.id \
            AND round.disputeID = dispute.id \
            AND dispute.subcourtID = :subcourtID",
            {'address': self.address, 'subcourtID': court_id}
        )
        return votes_in_court.first()[0]

    def all_votes(self):
        votes = (db.session.query(Vote, Round, Dispute)
                 .filter(func.lower(Vote.account) == self.address)
                 .filter(Vote.round_id == Round.id)
                 .filter(Dispute.id == Round.disputeID)
                 .order_by(Vote.round_id.desc())
                 .all()
                 )
        return votes

    def all_votes_paginated(self, page=0, per_page=10):
        votes = (db.session.query(Vote, Round, Dispute)
                 .filter(func.lower(Vote.account) == self.address)
                 .filter(Vote.round_id == Round.id)
                 .filter(Dispute.id == Round.disputeID)
                 .order_by(Vote.round_id.desc())
                 .paginate(page,
                           per_page,
                           error_out=False))
        return votes

    @property
    def stakings(self):
        stakings_query = JurorStake.query.filter(JurorStake.address == self.address).order_by(JurorStake.timestamp.desc())
        stakings = []
        for staking in stakings_query:
            stakings.append(staking)
        return stakings

    @property
    def stakings_nonZero(self):
        stakings_query = JurorStake.query.filter(JurorStake.address == self.address).order_by(JurorStake.timestamp.desc())
        stakings = []
        for staking in stakings_query:
            if staking.setStake > 0:
                stakings.append(staking)
        return stakings

    @property
    def totalStaked(self):
        stakings_query = JurorStake.query.filter(JurorStake.address == self.address).order_by(JurorStake.timestamp.desc())
        stake = 0
        for staking in stakings_query:
            stake += staking.setStake
        return stake

    @property
    def current_stakings_per_court(self):
        stakings_query = db.session.execute(
            "SELECT MAX(id), subcourtID FROM juror_stake \
            WHERE address = :address \
            group by subcourtID", {'address': self.address}
        )
        stakings = {}
        for sq in stakings_query:
            stakings[sq[1]] = JurorStake.query.get(sq[0])
        return stakings

    def current_amount_in_court(self, court_id):
        stakings = self.current_stakings_per_court
        if court_id in stakings:
            court_only_stakings = stakings[court_id].setStake
        else:
            court_only_stakings = 0.0

        court_and_children = court_only_stakings

        court = Court.query.get(court_id)
        for child_id in court.children_ids():
            if child_id in stakings:
                court_and_children += stakings[child_id].setStake

        return {
            'court_only': court_only_stakings,
            'court_and_children': court_and_children
        }

    def retention():
        jurorsDrawn = Juror.list()
        jurorsDrawn = set(map(lambda x: x['address'].lower(), jurorsDrawn))
        activeJurors = Juror.stakedJurors()
        activeJurors = set(activeJurors.keys())
        jurorsRetained = activeJurors.intersection(jurorsDrawn)
        return len(jurorsRetained)

    def adoption(days=30):
        """
        Select the first stake for address in the past days.
        This is usefull to get the adoption
        """
        filter_after = (datetime.today()-timedelta(days=days)).replace(hour=0,
                                                                       minute=0,
                                                                       second=0)
        # filter_after = datetime.strftime(filter_after, '%Y-%m-%d')
        lastStakes = db.session.execute(
            "SELECT id, address, timestamp, setStake, subcourtID \
                FROM juror_stake \
                WHERE id IN ( \
                    SELECT MAX(id) \
                    FROM juror_stake \
                    GROUP BY address,subcourtID);"
        ).fetchall()
        oldStakes = db.session.execute(
            "SELECT id, address, timestamp, setStake, subcourtID \
                FROM juror_stake \
                WHERE id IN ( \
                    SELECT MAX(id) \
                    FROM juror_stake \
                    GROUP BY address,subcourtID);"
        ).fetchall()

        newJuror = set()
        oldJuror = set()
        for stake in lastStakes:
            if isinstance(stake.timestamp, datetime):
                if stake.setStake > 0 and stake.timestamp >= filter_after:
                    newJuror.add(stake.address)
            else:
                if stake.setStake > 0 and datetime.strptime(stake.timestamp,'%Y-%m-%d %H:%M:%S.%f') >= filter_after:
                    newJuror.add(stake.address)

        for stake in oldStakes:
            if isinstance(stake.timestamp, datetime):
                if stake.timestamp < filter_after:
                    oldJuror.add(stake.address)
            else:
                if datetime.strptime(stake.timestamp,'%Y-%m-%d %H:%M:%S.%f') < filter_after:
                    oldJuror.add(stake.address)
        return newJuror.difference(oldJuror)


class JurorStake(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(50))
    subcourtID = db.Column(db.Integer, db.ForeignKey("court.id"), nullable=False)
    timestamp = db.Column(db.DateTime)
    setStake = db.Column(db.Float)
    txid = db.Column(db.String(100))
    blocknumber = db.Column(db.Integer)

    @staticmethod
    def last_blocknumber():
        return JurorStake.query.order_by(JurorStake.id.desc()).first().blocknumber


class Deposit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(50))
    cdate = db.Column(db.DateTime)
    amount = db.Column(db.Float)
    txid = db.Column(db.String(50))
    court_id = db.Column(db.Integer, db.ForeignKey("court.id"), nullable=False)
    token_contract = db.Column(db.String(50))  # FIXME

    @classmethod
    def total(cls):
        return cls.query.with_entities(func.sum(cls.amount)).all()[0][0]


class Visitor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dashboard = db.Column(db.Integer)
    map = db.Column(db.Integer)
    odds = db.Column(db.Integer)
    support = db.Column(db.Integer)
    graphs = db.Column(db.Integer)
    unknown = db.Column(db.Integer)

    def __init__(self):
        try:
            currentVisitors = db.session.query(Visitor).get(1)
            self.dashboard = currentVisitors.dashboard
            self.map = currentVisitors.map
            self.odds = currentVisitors.odds
            self.support = currentVisitors.support
            self.graphs = currentVisitors.graphs
            self.unknown = currentVisitors.unknown
        except Exception:
            self.dashboard = 0
            self.map = 0
            self.odds = 0
            self.support = 0
            self.graphs = 0
            self.unknown = 0
            db.session.add(self)
            db.session.commit()

    def __repr__(self):
        return f'Visitor({self.dashboard}, {self.map}, {self.odds}, {self.support}, {self.unknown})'

    def addVisit(self, page):
        currentVisitors = db.session.query(Visitor).get(1)
        if page == 'dashboard':
            currentVisitors.dashboard += 1
        elif page == 'odds':
            currentVisitors.odds += 1
        elif page == 'map':
            currentVisitors.map += 1
        elif page == 'support':
            currentVisitors.support += 1
        elif page == 'graphs':
            currentVisitors.graphs += 1
        else:
            currentVisitors.unknown += 1
        db.session.commit()

    @staticmethod
    def resetCounters():
        currentVisitors = db.session.query(Visitor).get(1)
        currentVisitors.dashboard = 0
        currentVisitors.odds = 0
        currentVisitors.map = 0
        currentVisitors.support = 0
        currentVisitors.unknown = 0
        db.session.commit()


class StakesEvolution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime)
    court = db.Column(db.Integer)
    staked = db.Column(db.Float)
    jurors = db.Column(db.Integer)

    @staticmethod
    def getStakes_ByCourt_ForEndDate(enddate=datetime.strftime(datetime.now(),
                                                               '%Y-%m-%d')):
        """
        Return a Dict with the total staked amount by court, considering the
        stakes made before the enddate value

        Parameters
        ----------
        enddate : string, optional
            DESCRIPTION. The default is datetime.strftime(datetime.now(),'%Y-%m-%d').
            Datetime in format %Y-%m-%d to filter the stakes upto this date.

        Returns
        -------
        parseStakes : dict
            DESCRIPTION. Dictionary with the total amount staked in each court.
            The court are the keys, the values are the total stake amount.

        """
        allStakes = db.session.execute(
            f"SELECT id,address,setStake, subcourtID \
                FROM juror_stake \
                WHERE id IN ( \
                    SELECT MAX(id) \
                    FROM juror_stake \
                    WHERE timestamp <= '{enddate}' \
                    GROUP BY address,subcourtID);"
        )
        parseStakes = {'timestamp': enddate}
        jurors_by_court = {}
        for courtID in range(0, Court().ncourts):
            jurors_by_court[courtID] = set()
            parseStakes[courtID] = {'stake': 0,
                                    'jurors': 0}

        for stake in allStakes:
            try:
                # sum the stake in the stake by court
                parseStakes[stake.subcourtID]['stake'] += stake.setStake
                if stake.setStake > 0:
                    # add the address to the set, the duplicated address will not be added
                    jurors_by_court[stake.subcourtID].add(stake.address.lower())
            except Exception as e:
                # this court is not in the dict, add the new key with the value
                logger.error(f"Error trying to add stake and jurors of the court {stake.subcourtID} to the dict")
                logger.error(e)
                parseStakes[stake.subcourtID]['stake'] = stake.setStake
                if stake.setStake > 0:
                    jurors_by_court[stake.subcourtID] = set()
                    jurors_by_court[stake.subcourtID].add(stake.address.lower())
        # add jurors count in the dict
        for court in jurors_by_court.keys():
            parseStakes[court]['jurors'] = len(jurors_by_court[court])

        # add the childs values into the totals of the parents courts
        parseStakes_withChilds = {'timestamp': parseStakes['timestamp']}
        for courtID in range(Court().ncourts-1, -1, -1):
            childs = Court.getAllCourtChilds(courtID)[::-1]
            jurors = jurors_by_court[courtID]
            staked = parseStakes[courtID]['stake']
            for child in childs:
                staked += parseStakes[child]['stake']
                jurors = jurors.union(jurors_by_court[child])
            parseStakes_withChilds[courtID] = {'stake': staked,
                                               'jurors': len(jurors)}
        return parseStakes_withChilds

    @staticmethod
    def addDateValues(data_dict):
        for key in data_dict.keys():
            if key != 'timestamp':
                db.session.add(StakesEvolution(timestamp=datetime.strptime(data_dict['timestamp'],
                                                                           '%Y-%m-%d'),
                                               court=key,
                                               staked=data_dict[key]['stake'],
                                               jurors=data_dict[key]['jurors']))
        db.session.commit()

    @staticmethod
    def getEvolutionByCourt(courtID):
        data = StakesEvolution.query.filter(StakesEvolution.court == courtID).all()
        listData = []
        for item in data:
            listData.append({'timestamp': item.timestamp,
                             'staked': item.staked,
                             'jurors': item.jurors})
        return listData

    @staticmethod
    def getEvolution():
        data = StakesEvolution.query.all()
        listData = {}
        for item in data:
            if item.court in listData.keys():
                listData[item.court].append({'timestamp': item.timestamp,
                                             'staked': item.staked,
                                             'jurors': item.jurors})
            else:
                listData[item.court] = [{'timestamp': item.timestamp,
                                         'staked': item.staked,
                                         'jurors': item.jurors}]
        return listData


class ContractMapper(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    address = db.Column(db.String(50))
    contract_name = db.Column(db.String(100))
    dapp_name = db.Column(db.String(100))

    def __repr__(self):
        return f'ContractMapper({self.address}, {self.name})'

    def __str__(self):
        return f"{self.name}"

    @staticmethod
    def searchName(address):
        DappsMapper = {
            '0x594ec762b59978c97c82bc36ab493ed8b1f1f368'.lower(): 'Realitio',
            '0x701cabaf65ed3974925fb94988842a29d2ce7aa3'.lower(): 'Realitio',
            '0xd47f72a2d1d0e91b0ec5e5f5d02b2dc26d00a14d'.lower(): 'Realitio',
            '0xd7e143715a4244634d74201959372e81a3623a2a'.lower(): 'Realitio',
            '0x126697b552b83f08c7ebebae8d13eae2871e4e1e'.lower(): 'Realitio',
            '0xb72103ee8819f2480c25d306eeab7c3382fba612'.lower(): 'Curate',
            '0x1E9c3b5f57974beAdbd8C28Ba918d85b8477C618'.lower(): 'Curate',
            '0x941b4A0dfDC7f15275A4cb6913b395647BB69Fc3'.lower(): 'Curate',
            '0x6f15Ca438992d9a4d7281E7E80381C4d904B2A24'.lower(): 'Curate',
            '0x99A0f0e0d9Ee776D791D2E55c215d05ccF7286fC'.lower(): 'Curate',
            '0x7884a7ADf697e18357087FE8F994669042Af4ae9'.lower(): 'Curate',
            '0x8eFfF9BB64ED3d766a26a18e873cf171E67BeCf2'.lower(): 'Curate',
            '0x250aa88c8f54f5e70b94214380342f0d53e42f6c'.lower(): 'Curate',
            '0x7f112a0dc0ac7be95ac3c58532485f60726bb42c'.lower(): 'Curate',
            '0x0d67440946949fe293b45c52efd8a9b3d51e2522'.lower(): 'T2CR',
            '0x916deab80dfbc7030277047cd18b233b3ce5b4ab'.lower(): 'T2CR',
            '0xcb4aae35333193232421e86cd2e9b6c91f3b125f'.lower(): 'T2CR',
            '0xe0cf18e8630545aa553f88079c75dae56b8fb304'.lower(): 'T2CR',
            '0xebcf3bca271b26ae4b162ba560e243055af0e679'.lower(): 'T2CR',
            '0x46580533db92c418a79f91b46df70283daef7f99'.lower(): 'Escrow',
            '0x135c573503f70dc290b1d60fe2e7f7eb114febd6'.lower(): 'Dispute Resolver',
            '0xc9a3cd210cc9c11982c3acf7b7bf9b1083242cb6'.lower(): 'Dispute Resolver',
            '0x799cb978dea5d6ca00ccb1794d3c3d4c89e40cd1'.lower(): 'Dispute Resolver',
            '0xd8bf5114796ed28aa52cff61e1b9ef4ec1f69a54'.lower(): 'Dispute Resolver',
            '0xf65c7560d6ce320cc3a16a07f1f65aab66396b9e'.lower(): 'Dispute Resolver',
            '0xc7e49251807780dFBbCA72778890B80bd946590B'.lower(): 'Onboarding Tester',
            '0xF339047C85d0dd2645F2bD802a1e8a5e7AF61053'.lower(): 'Curate',
            '0x2E3B10aBf091cdc53cC892A50daBDb432e220398'.lower(): 'Curate',
            '0xD8F8019c025C2Ba6745543D9a3C338DE1b98C103'.lower(): 'Linguo'
            }

        contract = ContractMapper().query.filter(ContractMapper.address == address.lower()).first()
        if contract:
            if contract.dapp_name != "Unknown":
                return contract.dapp_name
            else:
                print(f"Unknown dapp name with address {address}")
                return contract.contract_name
        else:
            logger.debug("Searching in HardCoded / Etherscan and adding to the database")
            if address.lower() in list(DappsMapper.keys()):
                dappName = DappsMapper[address.lower()]
            else:
                dappName = "Unknown"
            name = Etherscan.getContractName(address)
            if not name:
                name = "Unknown"
                logger.info(f"The address {address} could not be found neither in the Database or Etherscan")
            db.session.add(ContractMapper(address=address,
                                          contract_name=name,
                                          dapp_name=dappName))
            db.session.commit()
            logger.info(f"Contract {address} added to the DataBase with name {name}")
            return dappName
