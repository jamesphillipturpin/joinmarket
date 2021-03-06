#! /usr/bin/env python
from __future__ import absolute_import, print_function

import os
import sys
import datetime
import time
import random
import decimal
import ConfigParser
import csv
import threading
import copy

from joinmarket import Maker, IRCMessageChannel, OrderbookWatch
from joinmarket import blockchaininterface, BlockrInterface
from joinmarket import jm_single, get_network, load_program_config
from joinmarket import random_nick
from joinmarket import get_log, calc_cj_fee, debug_dump_object
from joinmarket import Wallet

config = ConfigParser.RawConfigParser()
config.read('joinmarket.cfg')
mix_levels = 5
nickname = random_nick()
nickserv_password = ''

import math
import random
PHI = (math.sqrt(5.0)+1.0)/2.0
phi = (math.sqrt(5.0)-1.0)/2.0

def is_prime(n):
  if n == 2 or n == 3: return True
  if n < 2 or n%2 == 0: return False
  if n < 9: return True
  if n%3 == 0: return False
  r = int(n**0.5)
  f = 5
  while f <= r:
    #print '\t',f
    if n%f == 0: return False
    if n%(f+2) == 0: return False
    f +=6
  return True

"""
# 24 hours per day, 29.530587981 days per synodic month.
# The 2*PHI/math.log(2) term is intended to make the
# prime numbers average out to about two months, so time 
# frames aren't biased towards being out-of-phas lunar effects.
# You might change 29.530587981 to 365.24 if you use the same
# wallet for much over a year.
"""
time_frame_ceiling = int(24*29.530587981*2*PHI/math.log(2))
output_size_min = jm_single().DUST_THRESHOLD # Use dust limit
min_profit = 1000 * math.pow(phi, random.random())
log_coefficient = math.log(min_profit)
stddev_log_coefficient = 0
standard_size = pow(10,8)
output_size = output_size_min
profit = min_profit
power_law = 0.5
stddev_power_law = 0.0

"""
# This gives a list of prime numbers from 2 to slightly above time_frame_ceiling
# This is used later to make sampling procedures random/arbitary/noisy without 
# introducing accidental resonance effects.
# (No prime number can factor another prime number thus there is no resonance 
# between time periods of two different prime numbers.)
"""
def compile_primes(time_frame_ceiling):
  list_primes = []
  prime_candidate=2
  adjusted_ceiling = int(time_frame_ceiling + math.log(time_frame_ceiling))+1
  for i in range(adjusted_ceiling):
    while (len(list_primes)<=i): 
      if is_prime(prime_candidate):
        list_primes.append(prime_candidate)
        prime_candidate+=1
      else:
        prime_candidate+=1
  return list_primes

"""
# This creates offers based on the power law previously
# found/assumed, that have stastical noise added to avoid
# reverse engineering of transaction history based on offers.
"""
def randomize_offer_levels(largest_mixdepth_size):
 global time_frame_ceiling
 global min_profit
 global PHI
 global list_primes
 global time_frame_ceiling
 global log_coefficient
 global standard_size
 global power_law
 global output_size_max 
 output_size_max = largest_mixdepth_size
 list_primes = compile_primes(time_frame_ceiling)
 list_types = ['absolute','relative']
 offer_levels = []
 number_of_levels = int(math.ceil(math.log(output_size_max / output_size_min)))
 output_size_next = output_size_min
 for level in range(number_of_levels):
  output_size = output_size_next
  output_size_next= int(output_size*math.exp(math.exp(random.random())))
  ratio = output_size_next / output_size 
  output_mean = math.sqrt(output_size*output_size_next)
  """
  # We add the sample noise back into our prices, 
  # but only as discounts. The idea here is to explore prices 
  # around the mean but capture market share by being willing 
  # to do deeper sales than markups. Thus coinjoins are 
  # usually 'on sale', sort of like alpacha socks.
  """
  dev_coeff = random.gauss(0,1)
  dev_coeff = max(dev_coeff, -PHI)
  dev_coeff = min(dev_coeff, phi)
  dev_exp  = random.gauss(0,1)
  dev_exp = max(dev_exp, -PHI-dev_coeff )
  dev_exp = min(dev_exp, phi-dev_coeff )

  guess_coefficient = math.exp(log_coefficient + dev_coeff * stddev_log_coefficient)
  guess_exponent = power_law + dev_exp*stddev_power_law
  profit=int(min_profit+guess_coefficient *math.pow(output_mean,guess_exponent))
  type_choice = random.choice(list_types)
  if type_choice == 'relative':
    profit = int(profit*pow(10,10)/output_mean)
  time_frame = 1.0*random.choice(list_primes)  
  price_increment = math.pow(PHI,(24.0/time_frame)*(ratio/PHI))
  offer_levels.append({'starting_size': float(output_size)/float(pow(10,8)), 'type':type_choice,'price_floor': profit,'price_increment': price_increment,'price_ceiling': None, 'time_frame': time_frame,})
 return offer_levels
offer_levels = randomize_offer_levels(100*pow(10,8))

#END CONFIGURATION

try:
    wallet_file = sys.argv[1]
    statement_file = os.path.join(
        'logs', 'yigen-statement-' + wallet_file[:-5] + '.csv')
except:
    sys.exit("You forgot to specify the wallet file.")

try:
    from myoscoffers import offer_levels
except:
    pass

try:
    x = config.get('YIELDGEN', 'offer_low')
    x = [r for r in csv.reader([x], skipinitialspace=True)][0]
    if len(x) == 1:
        offer_low = int(float(x[0]))
    elif len(x) == 2:
        offer_low = random.randrange(
            int(float(x[0])), int(float(x[1])))  #random
    elif len(x) > 2:
        assert False
except (ConfigParser.NoOptionError, ConfigParser.NoSectionError) as e:
    offer_low = None  # will use output_min_size

try:
    x = config.get('YIELDGEN', 'offer_high')
    x = [r for r in csv.reader([x], skipinitialspace=True)][0]
    if len(x) == 1:
        offer_high = int(float(x[0]))
    elif len(x) == 2:
        offer_high = random.randrange(
            int(float(x[0])), int(float(x[1])))  #random
    elif len(x) > 2:
        assert False
except (ConfigParser.NoOptionError, ConfigParser.NoSectionError) as e:
    offer_high = None  # max mix depth will be used

try:
    x = config.get('YIELDGEN', 'output_size_min')
    x = [r for r in csv.reader([x], skipinitialspace=True)][0]
    if len(x) == 1:
        output_size_min = int(float(x[0]))
    elif len(x) == 2:
        output_size_min = random.randrange(
            int(float(x[0])), int(float(x[1])))  #random
    elif len(x) > 2:
        assert False
except (ConfigParser.NoOptionError, ConfigParser.NoSectionError) as e:
    output_size_min = jm_single().DUST_THRESHOLD

# the above config parser code could be moved into a library for reuse

log = get_log()
log.debug(random.choice([
"Yield Generator Cicada.",
"An attempt to optimize Yield Generator Oscillator",
"Maximize profit, money velocity, and information leakage avoidance."
]))
if offer_low:
    log.debug('offer_low = ' + str(offer_low) + " (" + str(offer_low / 1e8) +
              " btc)")
if offer_high:
    log.debug('offer_high = ' + str(offer_high) + " (" + str(offer_high / 1e8) +
              " btc)")
else:
    log.debug('offer_high = Max Mix Depth')
if output_size_min != jm_single().DUST_THRESHOLD:
    log.debug('output_size_min = ' + str(output_size_min) + " (" + str(
        output_size_min / 1e8) + " btc)")

def sanity_check(offers):
    for offer in offers:
        if offer['ordertype'] == 'absorder':
            assert isinstance(offer['cjfee'], int)
        elif offer['ordertype'] == 'relorder':
            assert isinstance(offer['cjfee'], int) or isinstance(offer['cjfee'],
                                                                 float)
        assert offer['maxsize'] > 0
        assert offer['minsize'] > 0
        assert offer['minsize'] <= offer['maxsize']
        assert offer['txfee'] >= 0
        if offer_high:
            assert offer['maxsize'] <= offer_high
        assert (isinstance(offer['minsize'], int) or isinstance(offer['minsize'], long))
        assert (isinstance(offer['maxsize'], int) or isinstance(offer['maxsize'], long))
        assert isinstance(offer['txfee'], int)
        assert offer['minsize'] >= offer_low
        if offer['ordertype'] == 'absorder':
            profit_max = offer['cjfee'] - offer['txfee']
        elif offer['ordertype'] == 'relorder':
            profit_min = int(float(offer['cjfee']) *
                             offer['minsize']) - offer['txfee']
            profit_max = int(float(offer['cjfee']) *
                             offer['maxsize']) - offer['txfee']
            assert profit_min >= 1
        assert profit_max >= 1

def offer_data_chart(offers):
    has_rel = False
    for offer in offers:
        if offer['ordertype'] == 'relorder':
            has_rel = True
    offer_display = []
    header = 'oid'.rjust(4)
    header += 'type'.rjust(5)
    header += 'cjfee'.rjust(12)
    header += 'minsize btc'.rjust(15)
    header += 'maxsize btc'.rjust(15)
    header += 'txfee'.rjust(7)
    if has_rel:
        header += 'minrev'.rjust(11)
        header += 'maxrev'.rjust(11)
        header += 'minprof'.rjust(11)
        header += 'maxprof'.rjust(11)
    else:
        header += 'rev'.rjust(11)
        header += 'prof'.rjust(11)
    offer_display.append(header)
    for offer in offers:
        oid = str(offer['oid'])
        if offer['ordertype'] == 'absorder':
            ot = 'abs'
            cjfee = str(offer['cjfee'])
            minrev = '-'
            maxrev = offer['cjfee']
            minprof = '-'
            maxprof = int(maxrev - offer['txfee'])
        elif offer['ordertype'] == 'relorder':
            ot = 'rel'
            cjfee = str('%.8f' % (offer['cjfee'] * 100))
            minrev = str(int(offer['cjfee'] * offer['minsize']))
            maxrev = str(int(offer['cjfee'] * offer['maxsize']))
            minprof = int(minrev) - offer['txfee']
            maxprof = int(maxrev) - offer['txfee']
        line = oid.rjust(4)
        line += ot.rjust(5)
        line += cjfee.rjust(12)
        line += str('%.8f' % (offer['minsize'] / 1e8)).rjust(15)
        line += str('%.8f' % (offer['maxsize'] / 1e8)).rjust(15)
        line += str(offer['txfee']).rjust(7)
        if has_rel:
            line += str(minrev).rjust(11)
            line += str(maxrev).rjust(11)
            line += str(minprof).rjust(11)  # minprof
            line += str(maxprof).rjust(11)  # maxprof
        else:
            line += str(maxrev).rjust(11)
            line += str(maxprof).rjust(11)  # maxprof
        offer_display.append(line)
    return offer_display


def get_recent_transactions(time_frame, show=False):
    if not os.path.isfile(statement_file):
        return []
    reader = csv.reader(open(statement_file, 'r'))
    rows = []
    for row in reader:
        rows.append(row)
    rows = rows[1:]  # remove heading
    rows.reverse()
    rows = sorted(rows, reverse=True)  # just to be sure
    xrows = []
    display_lines = []
    amount_total, earned_total = 0, 0
    for row in rows:
        try:
            timestamp = datetime.datetime.strptime(row[0], '%Y/%m/%d %H:%M:%S')
            if timestamp < (datetime.datetime.now() - datetime.timedelta(
                    hours=time_frame)):
                break
            amount = int(row[1])
            my_input_count = int(row[2])
            my_input_value = int(row[3])
            cjfee = int(row[4])  # before txfee contrib
            cjfee_earned = int(row[5])
            confirm_time = float(row[6])
        except ValueError:
            continue
        effective_rate = float('%.10f' % (cjfee_earned / float(amount)))  # /0?
        amount_total += amount
        earned_total += cjfee_earned
        xrows.append({'timestamp': timestamp,
                      'amount': amount,
                      'cjfee_earned': cjfee_earned,
                      'confirm_time': confirm_time,})
        display_str = ' ' + timestamp.strftime("%Y-%m-%d %I:%M:%S %p")
        display_str += str(float(confirm_time)).rjust(13)
        display_str += str('%.8f' % (int(amount) / 1e8)).rjust(14)
        display_str += str(int(cjfee_earned)).rjust(13)
        display_str += str(('%.8f' % effective_rate) + ' %').rjust(16)
        display_lines.append(display_str)

    if show and display_lines:
        display = [
            ' datetime                confirm min    amount btc   earned sat   effectiverate'
        ]
        display = display + display_lines
        display.append('-------------------------------------------'.rjust(79))
        total_effective_rate = float('%.10f' %
                                     (earned_total / float(amount_total)))
        ter_str = str(('%.8f' % total_effective_rate) + ' %').rjust(16)
        display.append('Totals:'.rjust(36) + str('%.8f' % (
            amount_total / 1e8)).rjust(14) + str(earned_total).rjust(13) +
                       ter_str)
        time_frame_days = time_frame / 24.0
        log.debug(str(len(xrows)) + ' transactions in the last ' + str(
            time_frame) + ' hours: \n' + '\n'.join([str(x) for x in display]))
        #log.debug(str(len(xrows)) + ' transactions in the last ' + str(
        #    time_frame) + ' hours (' + str(time_frame_days) + ' days) = \n' +
        #          '\n'.join([str(x) for x in display]))
    elif show:
        log.debug('No transactions in the last ' + str(time_frame) + ' hours.')
    return xrows

# This is just a subtroutine for Find_Power_Law(...) function
# It finds the statistical correlation for a regression with
# a given value of C without doing the full regression.
def Compare_Power_Law_Correlation(amounts, earnings, C, correl_max, min_profit, weights=[]):
      log_amounts = [math.log(x) for x in amounts]
      # Points where x<=C wouldn't be valid transactions under
      # the power law corresponding to that value of C, so
      # using log(1)=0 in that case seems OK.
      log_earnings = [math.log(max(abs(x-C),1)) for x in earnings]
      correl = Correlation(log_amounts,log_earnings,weights)
      if correl > correl_max:
        correl_max = correl
        min_profit = C
      return [correl_max, min_profit]

"""
# Assumes power law model,
# earnings = A*math.pow(amount,B) + C
# Subtract C from both sides and apply logarithm to get
# log(earnings-C) = log(A)+B*log(amount)
# Substitute
# Y=log(earnings-C)
# Intercept = log(A)
# Slope = B
# X=log(amount)
# Thus Y=intercept+slope*X, which allows for linear regression
# To find the power loaw
# Finds C that will give best correlation
# Then uses linear regression to find best fit.
"""
def Find_Power_Law(largest_mixdepth_size, sorted_mix_balance):
    global min_profit
    global power_law
    global log_coefficient
    global correl
    global correl_max
    offer_lowx = max(offer_low, output_size_min)
    if offer_high:
        offer_highx = min(offer_high, largest_mixdepth_size - output_size_min)
    else:
        offer_highx = largest_mixdepth_size - output_size_min
    offers = []
    display_lines = []
    all_amounts = []
    all_earnings = []
    oid = 0
    offer_level_count = 0
    excess_offer_level_count = 0
    empty_offer_level_count = 0
    transactions_per_unit_time = 0.0
    min_earned = 2000.0
    correl_max = -99.9
    for offer in offer_levels:
        offer_level_count += 1
        if offer['starting_size'] > offer_highx:
            excess_offer_level_count +=1
        lower = int(offer['starting_size'] * 1e8)
        if lower < offer_lowx:
            lower = offer_lowx
        if offer_level_count <= len(offer_levels) - 1:
            upper = int((offer_levels[offer_level_count]['starting_size'] * 1e8) - 1)
            if upper > offer_highx:
                upper = offer_highx
        else:
            upper = offer_highx
        if lower > upper:
            continue
        fit_txs = []
        time_frame = offer['time_frame']
        for tx in get_recent_transactions(time_frame, show=False):
            if tx['amount'] >= lower and tx['amount'] <= upper:
                fit_txs.append(tx)
        amounts, earnings = [], []
        if fit_txs:
            amounts = [x['amount'] for x in fit_txs]
            earnings = [x['cjfee_earned'] for x in fit_txs]
            for x in fit_txs:
              min_earned = min(min_earned, x['cjfee_earned'])
            all_amounts += amounts
            all_earnings += earnings
            transactions_per_unit_time += len(fit_txs)/time_frame
        else:
            empty_offer_level_count += 1
    weights = Utility(all_earnings, all_amounts)
    #Grid search to find best value of C.
    start_C = 0
    end_C = int(mean(all_earnings))
    step_C = 2*(end_C-start_C)
    while (step_C>1):
      step_C = step_C/2+step_C%2
      range_C = range(start_C, end_C, step_C)
      for C in range_C:
        [correl_max, min_profit] = Compare_Power_Law_Correlation(all_amounts, all_earnings, C, correl_max, min_profit, weights)
      start_C = min_profit-step_C+1
      end_C = min_profit+step_C
    C = min_profit
    log_amounts = [math.log(x) for x in all_amounts]
    log_earnings = [math.log(max(abs(x-C),1)) for x in all_earnings]
    [pl,ap,correl,sd_pl,sd_ap]=Linear_Regression(log_amounts, log_earnings, weights)
    assert(correl == correl_max)
    power_law = pl
    intercept = ap
    stddev_power_law = sd_pl
    stddev_intercept = sd_ap
    offer_level_count -= excess_offer_level_count 
    offer_level_count -= empty_offer_level_count 
    log_coefficient = intercept-math.log(PHI)*transactions_per_unit_time/offer_level_count
    stddev_log_coefficient = stddev_intercept-math.log(PHI)*transactions_per_unit_time/offer_level_count
    assert(power_law > 0.0)
    assert(C >= 0)

# Returns statistical/arithmetic mean of elements in list X  
def mean(X,W=None):
    if W:
      L = len(X)
      sum_wx=0
      for i in range(L):
        sum_wx+=W[i]*X[i]
      return sum_wx/sum(W)
    else:
      return sum(X)/float(len(X))

def stddev(X, mean_x=None, W=None):
  L=len(X)
  var=0
  if not mean_x:
    mean_x = mean(X, W)
  if not W:
    for x in X:
      x_norm = x-mean_x
      var+=x_norm*x_norm
  else:
    for i in range(L):
      x=X[i]
      w=W[i]
      x_norm = x-mean_x
      var+=x_norm*x_norm*w
    var/=sum(W)
  return math.sqrt(var)

"""
# The utility function is intended to allow users to weight 
# data points in either specific or random manner.
# In this case we pick a random "per transaction" weight
# And a random "logarithm of earnings" weight.
# The idea is that we may wish to weight high earnings or
# high amount transactions more since that is where most
# of our earnings come from.
# We do wish to avoid purely linear weight with earnings as
# that emphasizes high outliers and could create stagnation,
# so we could rely instead on log_earnings.
# The calculation of bitcoin days destroyed is not
# yet implemented, so we must rely on amounts for now.
# Although the idea here is to allow each user to cater 
# Utility function to his preferences, the default random 
# weights are intended to be fairly general purpose, to span
# a range of reasonably likely preferences, from high number of
# raw transactions to high earnings per transaction, from 
# high earnings per amount (interest per transaction) to high
# movement between mixed depths - and any mixture of those.
"""
def Utility(earnings, amounts):
    L = len(earnings)
    Per_Transaction_Weight = random.random()
    Weight_Log_Earnings = random.random()
    Weight_Log_Amounts = random.random()
    weights = L*[Per_Transaction_Weight]
    log_earnings = [math.log(x) for x in earnings]
    log_amounts = [math.log(x) for x in amounts]
    mean_log_earnings = mean(log_earnings)
    mean_log_amounts = mean(log_amounts)
    stddev_log_earnings = stddev(log_earnings, mean_log_earnings)
    stddev_log_amounts = stddev(log_amounts, mean_log_amounts)
    norm_log_earnings = Normalize(log_earnings, mean_log_earnings, stddev_log_earnings,1.0)
    norm_log_amounts = Normalize(log_amounts, mean_log_amounts, stddev_log_amounts,1.0)
    for i in range(L):
      weights[i] += Weight_Log_Earnings * norm_log_earnings[i]
      weights[i] += Weight_Log_Amounts * norm_log_amounts[i]
    return weights

def Normalize(X, mean_X, stddev_X, offset = 0.0):
  L=len(X)
  result=[]
  for i in range(L):
    result.append((X[i]-mean_X)/stddev_X+offset)
  return result

# Returns statistical correlation between elements in two lists.
# With weights W
def Correlation(X,Y,W=None):
    L = len(X)
    mean_x = mean(X,W)
    mean_y = mean(Y,W)
    covariance = 0.0
    SS_xx = 0.0
    SS_yy = 0.0
    if W:
      for i in range(L):
        x=X[i]
        y=Y[i]
        w=W[i]
        x_norm = (x-mean_x)
        y_norm = (y-mean_y)
        # Technically covariance is this divided by sum(W)
        # But the sum(W)'s would cancel so we just drop them.
        covariance += x_norm * y_norm * w 
        SS_xx += x_norm * x_norm * w
        SS_yy += y_norm * y_norm * w
    else:
      for i in range(L):
        x=X[i]
        y=Y[i]
        x_norm = (x-mean_x)
        y_norm = (y-mean_y)
        covariance += x_norm * y_norm
        SS_xx += x_norm * x_norm
        SS_yy += y_norm * y_norm
    correl = covariance/math.sqrt(SS_xx*SS_yy)
    return correl

"""
# Linear regression to determine best fit of form
# Y[i] = slope*X[i]+intercept
# Returns [slope, intercept, correlation,
# uncertainty of slope, uncertainty of intercepe] in a list.
# (Uncertainty is basically standard deviation in this case.)
"""
def Linear_Regression(X,Y,W=None):
    Covariance  = 0.0
    SS_xx = 0.0
    SS_yy = 0.0
    L = len(X)
    mean_x = mean(X,W)
    mean_y = mean(Y,W)
    if W:
      for i in range(L):
        x=X[i]
        y=Y[i]
        w=W[i]
        x_norm = (x-mean_x)
        y_norm = (y-mean_y)
        Covariance  += x_norm * y_norm * w
        SS_xx += x_norm * x_norm * w
        SS_yy += y_norm * y_norm * w
      slope = Covariance /SS_xx
      intercept = mean_y-slope*mean_x
      correl = Covariance /math.sqrt(SS_xx*SS_yy)
      exp_y_x = [(slope*X[i]+intercept) for i in range(L)]
      var_y_given_x = sum([math.pow(Y[i]-exp_y_x[i],2) for i in range(L)])/float(L-2)
      var_slope = var_y_given_x / SS_xx 
      var_intercept = var_slope * (1.0/L + mean_x*mean_x/SS_xx)
      return [slope, intercept, correl, math.sqrt(var_slope), math.sqrt(var_intercept)]
    else:
      for i in range(L):
        x=X[i]
        y=Y[i]
        x_norm = (x-mean_x)
        y_norm = (y-mean_y)
        Covariance  += x_norm * y_norm
        SS_xx += x_norm * x_norm
        SS_yy += y_norm * y_norm
      slope = Covariance /SS_xx
      intercept = mean_y-slope*mean_x
      correl = Covariance /math.sqrt(SS_xx*SS_yy)
      exp_y_x = [(slope*X[i]+intercept) for i in range(L)]
      var_y_given_x = sum([math.pow(Y[i]-exp_y_x[i],2) for i in range(L)])/float(L-2)
      var_slope = var_y_given_x / SS_xx 
      var_intercept = var_slope * (1.0/L + mean_x*mean_x/SS_xx)
      return [slope, intercept, correl, math.sqrt(var_slope), math.sqrt(var_intercept)]

def create_oscillator_offers(largest_mixdepth_size, sorted_mix_balance):
    Find_Power_Law(largest_mixdepth_size, sorted_mix_balance)
    offer_levels = randomize_offer_levels(largest_mixdepth_size)
    offer_lowx = max(offer_low, output_size_min)
    if offer_high:
        offer_highx = min(offer_high, largest_mixdepth_size - output_size_min)
    else:
        offer_highx = largest_mixdepth_size - output_size_min
    offers = []
    display_lines = []
    oid = 0
    count = 0
    for offer in offer_levels:
        count += 1
        lower = int(offer['starting_size'] * 1e8)
        if lower < offer_lowx:
            lower = offer_lowx
        if count <= len(offer_levels) - 1:
            upper = int((offer_levels[count]['starting_size'] * 1e8) - 1)
            if upper > offer_highx:
                upper = offer_highx
        else:
            upper = offer_highx
        if lower > upper:
            continue
        fit_txs = []
        for tx in get_recent_transactions(offer['time_frame'], show=False):
            if tx['amount'] >= lower and tx['amount'] <= upper:
                fit_txs.append(tx)
        amounts, earnings = [], []
        size_avg, earn_avg, effective_rate = 0, 0, 0
        if fit_txs:
            amounts = [x['amount'] for x in fit_txs]
            earnings = [x['cjfee_earned'] for x in fit_txs]
            size_avg = sum(amounts) / len(amounts)
            earn_avg = sum(earnings) / len(earnings)
            if size_avg:
              effective_rate = float('%.10f' %
                                   (sum(earnings) / float(sum(amounts))))  # /0?
        if isinstance(offer['price_increment'], int):
            tpi = offer['price_increment'] * len(fit_txs)
            cjfee = offer['price_floor'] + tpi
        elif isinstance(offer['price_increment'], float):
            tpi = offer['price_increment']**len(fit_txs)
            cjfee = int(round(offer['price_floor'] * tpi))
        else:
            sys.exit('bad price_increment: ' + str(offer['price_increment']))
        if offer['price_ceiling'] and cjfee > offer['price_ceiling']:
            cjfee = offer['price_ceiling']
        assert offer['type'] in ('absolute', 'relative')
        if offer['type'] == 'absolute':
            ordertype = 'absorder'
        elif offer['type'] == 'relative':
            ordertype = 'relorder'
            cjfee = float('%.10f' % (cjfee / 1e10))
        oid += 1
        offerx = {'oid': oid,
                  'ordertype': ordertype,
                  'minsize': lower,
                  'maxsize': upper,
                  'txfee': 0,
                  'cjfee': cjfee}
        offers.append(offerx)
        display_line = ''
        display_line += str('%.8f' % (lower / 1e8)).rjust(15)
        display_line += str('%.8f' % (upper / 1e8)).rjust(15)
        display_line += str(offer['time_frame']).rjust(8)
        display_line += str(len(fit_txs)).rjust(8)
        display_line += str('%.8f' % (size_avg / 1e8)).rjust(15)
        display_line += str(earn_avg).rjust(10)
        display_line += str('%.8f' % (sum(amounts) / 1e8)).rjust(15)
        display_line += str(sum(earnings)).rjust(10)
        display_line += str('%.8f' % effective_rate).rjust(13) + ' %'
        display_lines.append(display_line)
    newoffers = []
    for offer in offers:
        if not newoffers:
            newoffers.append(offer)
            continue
        last_offer = copy.deepcopy(newoffers[-1])
        if (offer['minsize'] == last_offer['maxsize'] or \
            offer['minsize'] == last_offer['maxsize'] + 1) and \
            offer['cjfee'] == last_offer['cjfee']:
            assert offer['txfee'] == last_offer['txfee']
            newoffers = newoffers[:-1]
            last_offer['maxsize'] = offer['maxsize']
            newoffers.append(last_offer)
        else:
            newoffers.append(offer)
    get_recent_transactions(24, show=True)
    display = ['-------averages-------   --------totals--------'.rjust(93)]
    display.append(
        '    minsize btc    maxsize btc   hours     txs       size btc  ' +
        'earn sat       size btc  earn sat  effectiverate')
    log.debug('range summaries: \n' + '\n'.join([str(
        x) for x in display + display_lines]))
    log.debug('offer data chart: \n' + '\n'.join([str(
        x) for x in offer_data_chart(offers)]))
    if offers != newoffers:
        #oid = 1
        #for offer in newoffers:
        #    offer['oid'] = oid
        #    oid += 1
        log.debug('final compressed offer data chart: \n' + '\n'.join([str(
            x) for x in offer_data_chart(newoffers)]))
    #log.debug('oscillator offers = \n' + '\n'.join([str(x) for x in offers]))
    #log.debug('oscillator offers compressed = \n' + '\n'.join([str(
    #    o) for o in newoffers]))
    return newoffers


class YieldGenerator(Maker, OrderbookWatch):

    def __init__(self, msgchan, wallet):
        Maker.__init__(self, msgchan, wallet)
        self.msgchan.register_channel_callbacks(self.on_welcome,
                                                self.on_set_topic, None, None,
                                                self.on_nick_leave, None)
        self.tx_unconfirm_timestamp = {}

    def on_welcome(self):
        Maker.on_welcome(self)
        if not os.path.isfile(statement_file):
            log.debug('Creating ' + str(statement_file))
            self.log_statement(
                ['timestamp', 'cj amount/satoshi', 'my input count',
                 'my input value/satoshi', 'cjfee/satoshi', 'earned/satoshi',
                 'confirm time/min', 'notes'])
        timestamp = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        self.log_statement([timestamp, '', '', '', '', '', '', 'Connected'])

    def create_my_orders(self):
        mix_balance = self.wallet.get_balance_by_mixdepth()
        log.debug('mix_balance = ' + str(mix_balance))
        total_balance = 0
        for num, amount in mix_balance.iteritems():
            log.debug('for mixdepth=%d balance=%.8fbtc' % (num, amount / 1e8))
            total_balance += amount
        log.debug('total balance = %.8fbtc' % (total_balance / 1e8))
        sorted_mix_balance = sorted(
            list(mix_balance.iteritems()),
            key=lambda a: a[1])  #sort by size
        largest_mixdepth_size = sorted_mix_balance[-1][1]
        if largest_mixdepth_size == 0:
            print("ALERT: not enough funds available in wallet")
            return []
        offers = create_oscillator_offers(largest_mixdepth_size,
                                          sorted_mix_balance)
        log.debug('offer_data_chart = \n' + '\n'.join([str(
            x) for x in offer_data_chart(offers)]))
        sanity_check(offers)
        log.debug('offers len = ' + str(len(offers)))
        log.debug('generated offers = \n' + '\n'.join([str(o) for o in offers]))
        return offers

    def oid_to_order(self, cjorder, oid, amount):
        '''Coins rotate circularly from max mixdepth back to mixdepth 0'''
        mix_balance = self.wallet.get_balance_by_mixdepth()
        total_amount = amount + cjorder.txfee
        log.debug('amount, txfee, total_amount = ' + str(amount) + str(
            cjorder.txfee) + str(total_amount))

        # look for exact amount available with no change
        # not supported because change output required
        # needs this fixed https://github.com/JoinMarket-Org/joinmarket/issues/418
        #filtered_mix_balance = [m
        #                        for m in mix_balance.iteritems()
        #                        if m[1] == total_amount]
        #if filtered_mix_balance:
        #    log.debug('mix depths that have the exact amount needed = ' + str(
        #        filtered_mix_balance))
        #else:
        #    log.debug('no mix depths contain the exact amount needed.')

        filtered_mix_balance = [m
                                for m in mix_balance.iteritems()
                                if m[1] >= (total_amount)]
        log.debug('mix depths that have enough = ' + str(filtered_mix_balance))
        filtered_mix_balance = [m
                                for m in mix_balance.iteritems()
                                if m[1] >= total_amount + output_size_min]
        log.debug('mix depths that have enough with output_size_min, ' + str(
            filtered_mix_balance))
        try:
            len(filtered_mix_balance) > 0
        except Exception:
            log.debug('No mix depths have enough funds to cover the ' +
                      'amount, cjfee, and output_size_min.')
            return None, None, None

        # slinky clumping: push all coins towards the largest mixdepth,
        # then spend from the largest mixdepth into the next mixdepth.
        # the coins stay in the next mixdepth until they are all there,
        # and then get spent into the next mixdepth, ad infinitum.
        lmd = sorted(filtered_mix_balance, key=lambda x: x[1],)[-1]
        smb = sorted(filtered_mix_balance, key=lambda x: x[0])  # seq of md num
        mmd = self.wallet.max_mix_depth
        nmd = (lmd[0] + 1) % mmd
        if nmd not in [x[0] for x in smb]:  # use all usable
            next_si = (smb.index(lmd) + 1) % len(smb)
            filtered_mix_balance = smb[next_si:] + smb[:next_si]
        else:
            nmd = [x for x in smb if x[0] == nmd][0]
            others = [x for x in smb if x != nmd and x != lmd]
            if not others:  # just these two remain, prioritize largest
                filtered_mix_balance = [lmd, nmd]
            else:  # use all usable
                if [x for x in others if x[1] >= nmd[1]]:
                    next_si = (smb.index(lmd) + 1) % len(smb)
                    filtered_mix_balance = smb[next_si:] + smb[:next_si]
                else:  # others are not large, dont use nmd
                    next_si = (smb.index(lmd) + 2) % len(smb)
                    filtered_mix_balance = smb[next_si:] + smb[:next_si]

        # prioritize by mixdepths ascending
        # keep coins moving towards last mixdepth, clumps there.
        # makes sure coins sent to mixdepth 0 will get mixed to mixdepth 5
        #filtered_mix_balance = sorted(filtered_mix_balance, key=lambda x: x[0])

        # use mix depth with the most coins, 
        # creates a more even distribution across mix depths
        # and a more diverse txo selection in each depth
        # sort largest to smallest amount
        #filtered_mix_balance = sorted(filtered_mix_balance, key=lambda x: x[1], reverse=True)

        # use a random usable mixdepth. 
        # warning, could expose more txos to malicous taker requests
        #filtered_mix_balance = [random.choice(filtered_mix_balance)]

        log.debug('sorted order of filtered_mix_balance = ' + str(
            filtered_mix_balance))
        mixdepth = filtered_mix_balance[0][0]
        log.debug('filling offer, mixdepth=' + str(mixdepth))
        # mixdepth is the chosen depth we'll be spending from
        cj_addr = self.wallet.get_internal_addr((mixdepth + 1) %
                                                self.wallet.max_mix_depth)
        change_addr = self.wallet.get_internal_addr(mixdepth)
        utxos = self.wallet.select_utxos(mixdepth, total_amount)
        my_total_in = sum([va['value'] for va in utxos.values()])
        real_cjfee = calc_cj_fee(cjorder.ordertype, cjorder.cjfee, amount)
        change_value = my_total_in - amount - cjorder.txfee + real_cjfee
        if change_value <= output_size_min:
            log.debug('change value=%d below dust threshold, finding new utxos'
                      % (change_value))
            try:
                utxos = self.wallet.select_utxos(mixdepth,
                                                 total_amount + output_size_min)
            except Exception:
                log.debug(
                    'dont have the required UTXOs to make a output above the dust threshold, quitting')
                return None, None, None
        return utxos, cj_addr, change_addr

    def refresh_offers(self):
        cancel_orders, ann_orders = self.get_offer_diff()
        self.modify_orders(cancel_orders, ann_orders)

    def get_offer_diff(self):
        neworders = self.create_my_orders()
        oldorders = self.orderlist
        new_setdiff_old = [o for o in neworders if o not in oldorders]
        old_setdiff_new = [o for o in oldorders if o not in neworders]
        neworders = sorted(neworders, key=lambda x: x['oid'])
        oldorders = sorted(oldorders, key=lambda x: x['oid'])
        if neworders == oldorders:
            log.debug('No orders modified for ' + nickname)
            return ([], [])
        """
        if neworders:
            log.debug('neworders = \n' + '\n'.join([str(o) for o in neworders]))
        if oldorders:
            log.debug('oldorders = \n' + '\n'.join([str(o) for o in oldorders]))
        if new_setdiff_old:
            log.debug('new_setdiff_old = \n' + '\n'.join([str(
                o) for o in new_setdiff_old]))
        if old_setdiff_new:
            log.debug('old_setdiff_new = \n' + '\n'.join([str(
                o) for o in old_setdiff_new]))
        """
        ann_orders = new_setdiff_old
        ann_oids = [o['oid'] for o in ann_orders]
        cancel_orders = [o['oid']
                         for o in old_setdiff_new if o['oid'] not in ann_oids]
        """
        if cancel_orders:
            log.debug('can_orders = \n' + '\n'.join([str(o) for o in
                                                     cancel_orders]))
        if ann_orders:
            log.debug('ann_orders = \n' + '\n'.join([str(o) for o in ann_orders
                                                    ]))
        """
        return (cancel_orders, ann_orders)

    def log_statement(self, data):
        if get_network() == 'testnet':
            return
        data = [str(d) for d in data]
        log.debug('Logging to ' + str(statement_file) + ': ' + str(data))
        assert len(data) == 8
        if data[7] == 'unconfirmed':  # workaround
            # on_tx_unconfirmed is being called by on_tx_confirmed
            for row in csv.reader(open(statement_file, 'r')):
                lastrow = row
            if lastrow[1:6] == data[1:6]:
                log.debug('Skipping double csv entry, workaround.')
                pass
            else:
                fp = open(statement_file, 'a')
                fp.write(','.join(data) + '\n')
                fp.close()
        elif data[7] != '':  # 'Connected', 'notes'
            fp = open(statement_file, 'a')
            fp.write(','.join(data) + '\n')
            fp.close()
        else:  # ''
            rows = []
            for row in csv.reader(open(statement_file, 'r')):
                rows.append(row)
            fp = open(statement_file, 'w')
            for row in rows:
                if row[1:] == data[1:6] + ['0', 'unconfirmed']:
                    fp.write(','.join(data) + '\n')
                    log.debug('Found unconfirmed row, replacing.')
                else:
                    fp.write(','.join(row) + '\n')
            fp.close()

    def on_tx_unconfirmed(self, cjorder, txid, removed_utxos):
        self.tx_unconfirm_timestamp[cjorder.cj_addr] = int(time.time())
        timestamp = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        my_input_value = sum([av['value'] for av in cjorder.utxos.values()])
        earned = cjorder.real_cjfee - cjorder.txfee
        self.log_statement([timestamp, cjorder.cj_amount, len(
            cjorder.utxos), my_input_value, cjorder.real_cjfee, earned, '0',
                            'unconfirmed'])
        self.refresh_offers()  # for oscillator
        return self.get_offer_diff()

    def on_tx_confirmed(self, cjorder, confirmations, txid):
        if cjorder.cj_addr in self.tx_unconfirm_timestamp:
            confirm_time = int(time.time()) - self.tx_unconfirm_timestamp[
                cjorder.cj_addr]
            confirm_time = round(confirm_time / 60.0, 2)
            del self.tx_unconfirm_timestamp[cjorder.cj_addr]
        else:
            confirm_time = 0
        timestamp = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        my_input_value = sum([av['value'] for av in cjorder.utxos.values()])
        earned = cjorder.real_cjfee - cjorder.txfee
        self.log_statement([timestamp, cjorder.cj_amount, len(
            cjorder.utxos), my_input_value, cjorder.real_cjfee, earned,
                            confirm_time, ''])
        return self.on_tx_unconfirmed(cjorder, txid, None)


def main():
    load_program_config()
    if isinstance(jm_single().bc_interface,
                  blockchaininterface.BlockrInterface):
        print('You are using the blockr.io website')
        print('You should setup JoinMarket with Bitcoin Core.')
        ret = raw_input('\nContinue Anyways? (y/n):')
        if ret[0] != 'y':
            return
    wallet = Wallet(wallet_file, max_mix_depth=mix_levels)
    jm_single().bc_interface.sync_wallet(wallet)
    jm_single().nickname = nickname
    log.debug('starting yield generator')
    irc = IRCMessageChannel(jm_single().nickname,
                            realname='btcint=' + jm_single().config.get(
                                "BLOCKCHAIN", "blockchain_source"),
                            password=nickserv_password)
    maker = YieldGenerator(irc, wallet)

    def timer_loop(startup=False):  # for oscillator
        if not startup:
            maker.refresh_offers()
        poss_refresh = []
        for x in offer_levels:
            recent_transactions = get_recent_transactions(x['time_frame'])
            if recent_transactions:
                oldest_transaction_time = recent_transactions[-1]['timestamp']
            else:
                oldest_transaction_time = datetime.datetime.now()
            next_refresh = oldest_transaction_time + datetime.timedelta(
                hours=x['time_frame'],
                seconds=1)
            poss_refresh.append(next_refresh)
        next_refresh = sorted(poss_refresh, key=lambda x: x)[0]
        td = next_refresh - datetime.datetime.now()
        seconds_till = (td.days * 24 * 60 * 60) + td.seconds
        log.debug('Next offer refresh for ' + nickname + ' at ' +
                  next_refresh.strftime("%Y-%m-%d %I:%M:%S %p"))
        log.debug('...or after a new transaction shows up.')
        t = threading.Timer(seconds_till, timer_loop)
        t.daemon = True
        t.start()

    timer_loop(startup=True)
    try:
        log.debug('connecting to irc')
        irc.run()
    except:
        log.debug('CRASHING, DUMPING EVERYTHING')
        debug_dump_object(wallet, ['addr_cache', 'keys', 'seed'])
        debug_dump_object(maker)
        debug_dump_object(irc)
        import traceback
        log.debug(traceback.format_exc())


if __name__ == "__main__":
    main()
    print('done')
