"""
-----------------------------------------------
--------------- NashEq Finder -----------------
-----------------------------------------------
This script is a python implementation of the NashEq Finder algorithm presented in

Zomorrodi, AR, Segre, D, "Microbial games at genomic resolution: understanding the 
evolution of intercellular metabolic interactions in microbial communities", Nat Comm (2017)

This code can identify all pure strategy Nash equilibria of a game with any number of players
and strategies inone shot.

NOTE:
1. This code requires installing pyomor, which is a python-based optimization modeling software package
   Check out the followingn link for details:
   http://www.pyomo.org

2. This code also requires an optimizaton solver such as gurobo or IBM cplex. Consult the respected 
   website for further details.   

Ali R. Zomorrodi, Segre Lab @ Boston University
Last updated: July 06th, 2017

Please contact Ali Zomorrodi at ali.r.zomorrodi@gmail.com for questions and updates

"""

from __future__ import division
import re, sys, math, copy, time, random
from datetime import timedelta
from numpy import nonzero  # To convert elapsed time to hh:mm:ss format
from pyomo.environ import *
from pyomo.opt import *
from sympy.sets.sets import FiniteSet
sys.path.append('/Users/elieeshoa/Dropbox/Elie_Eshoa/Ali_codes/')
from pyomoSolverCreator import *
import optlang
import sympy

# The following lines change the temporary directory for pyomo
# from pyutilib.services import TempfileManager
# TempfileManager.tempdir = pyomo_tmp_dir

class NashEqFinder(object):
    """
    General class for NashEq Finder. Sample usage is provided at the end 
    """   

    def __init__(self, game, NashEq_type = 'pure', optimization_solver = 'gurobi', warnings = True, stdout_msgs = True, output_file = ''):
        """
        INPUTS 
        ------
        game: 
        An instance of the class game (see game.py for details) 

        NashEq_type:
        Type of the Nash equilibrium to find (currently only pure strategy Nash equilibrium)

        optimization_solver: 
        Name of the LP solver to be used to solve the LP. Current 
        allowable choices are cplex and gurobi

        warnings: 
        Can be True or False indicating whether warnings should be written 
        in the standard output

        stdout_msgs: 
        By default (True) writes a summary including the solve 
        status, optimality status (if not optimal), objective 
        function value and the elapsed time on the screen.
        if set to a value of False no resuults are written on 
        the screen, in which case The user can instead specifiy 
        an output file using the option output_file, or store 
        them in a variable (see the 'run' method for details)

        output_file: 
        Optional input. It is a string containg the path to a 
        file and its name (e.g., 'results/fbaResults.txt'), where
        the results should be written to. 
        """
       
        # Metabolic model
        self.game = game

        # Type of the Nash equilibrium to find
        if NashEq_type.lower() not in ['pure','mixed']:
            raise ValueError("Invalid NashEq_type (allowed choices are 'pure' or 'mixed')")
        else:
            self.NashEq_type = NashEq_type

        # Solver name
        if optimization_solver == None:
            self.optimization_solver = 'gurobi'
        else:
            if optimization_solver.lower() in ['cplex','gurobi']:
                self.optimization_solver = optimization_solver
            else:
                raise ValueError('Invalid solver name (eligible choices are cplex and gurobi)\n')          
               
        # Output to the screen 
        if not isinstance(warnings,bool):
            raise TypeError("Error! warnings should be True or False")
        else:
             self.warnings = warnings

        if not isinstance(stdout_msgs,bool):
            raise TypeError("Error! stdout_msgs should be True or False")
        else:
             self.stdout_msgs = stdout_msgs

        # Output file
        if not isinstance(output_file, str):
            raise TypeError('output_file must be a string')
        else:
            self.output_file = output_file

        # Lower bound on payoff values according to the payoff matrix
        payoffMin = min([k for sublist in self.game.payoff_matrix.values() for k in sublist.values()]) 

        # Sometimes we run into problems when both LB and max payoff of a plyaer given
        # the fixed strategies of other players are zero (i.e., we arrive at a trivial
        # solution of e.g., 2 >= 0 as both terms in the RHS of constraint NashCond are
        # Cancelled out. This happens for problem 9 of Homework 1 of Game Theory I
        # for example). Therefore, it is better to always avoid a LB of zero. 
        if payoffMin - 1 > 0: 
            self.payoffLB = payoffMin - 1 
        else:
            self.payoffLB = payoffMin - 2 

    def convert_to_payoffMatrix_key(self,i):
        """
        This function converts the elements of the set I in the pyomo model
        (or elements of gameStatesForI) to the format of keys of the payoff matrix
        of the game, i.e., ('p1','s1','p2','s2') is converted to (('p1','s1'),('p2','s2')) 
        (see optModel.I for details)
        """
        gameState = []
        done = 0
        k1 = list(i)
        while done == 0:
            gameState.append(tuple(k1[0:2]))
            # print('tuple(k1[0:2])', tuple(k1[0:2]))
            del k1[0:2]
            if len(k1) == 0:
                done = 1
        return tuple(gameState)

        
    def createPyomoModel(self):
        """
        This creates a pyomo optimization model 

        Instead of several indicies for binary variables (y), we just define a single set I containing all
        possible labels of the payoff matrix (combinations of players and strategies). 
        """   
        #--- Create a pyomo model optModel ---
        optModel = ConcreteModel()
        # optlangOptModel = optlang.interface.Model(name='Original Model')
        
        #--- Define sets ---
        # Set of players
        optModel.P = Set(initialize = self.game.players_names) 
        optModel.P.pprint()  
        # players = self.game.players_names

        # Set of players' strategy combinations 
        # Keys of the game.payoff_matrix are in the form of a list of tuples, where each
        # tuple is compased of inner tuple of length two, e.g., 
        # [(('p1','s1'),('p2','s2')),(('p1','s2'),('p2','s1')),...]
        # These keys should serve as the elements of the set I in the optimization model,
        # however, pyomo does not accept list of tuples with nested tuples. Therefore, we 
        # need to convert this to a list of tuples with no inner tuples, i.e.,
        # [('p1','s1','p2','s2'),('p1','s2','p2','s1'),...]
        
        # optlangInit = [tuple([k3 for k2 in k1 for k3 in k2]) for k1 in self.game.payoff_matrix.keys()]
        optModel.I = Set(initialize = [tuple([k3 for k2 in k1 for k3 in k2]) for k1 in self.game.payoff_matrix.keys()])   
        # I = Set(initialize = [tuple([k3 for k2 in k1 for k3 in k2]) for k1 in self.game.payoff_matrix.keys()])   
        optModel.I.pprint()


        #--- Define the variables --- 
        optModel.y = Var(optModel.I, domain=Boolean)
        optModel.y.pprint()
        # Y = []
        # for element in optlangInit:
        #     str_element = str(element).replace(" ", "").replace('(', "").replace(')', "").replace("'","")
        #     y = optlang.interface.Variable(str_element, type='binary',problem=optlangOptModel)
        #     optlangOptModel.add(y)
        #     Y.append(str_element.replace('(', "").replace(')', "").replace("'",""))

        #--- Define the objective function and constraints ----
        # Objective function
        optModel.objective_rule = Objective(rule = lambda optModel: sum(optModel.y[i] for i in optModel.I), sense = maximize)
        # print("A variable value:", optModel.y[('row','C','column','D')])
        # print('type ', type(optModel.y[('row','C','column','D')]))
        # print('type ', type(optModel))
        # optModel.objective_rule.pprint()
        # optModel.pprint()
        # print(lambda optModel: sum(optModel.y[i] for i in optModel.I))
        # print(optlangOptModel.variables["('row','C','column','C')"])
        # print(sum(optlangOptModel.(str(i).replace(" ", "")) for i in optlangInit))

        # OPTLANG
        # print('type ', type(optlangOptModel.variables["row,C,column,D"]))
        # print('type ', type(optlangOptModel))
        # print(sum(optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","")] for i in optlangInit))
        # # print(sum(optlangOptModel.variables[str(i).replace(" ", "")] for i in optlangInit))
        
        # optlangVars = optlangOptModel.variables
        # print(optlangVars)
        # # lambda Y[row,C,column,D] : 1 + ('row','C','column','C')
        # optlang.interface.Objective(expression= sum(optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","")] for i in optlangInit), direction='max')

        # Constraint checking the best strategy of player p given the strategy of 
        # all other players 
        def NashCond_rule(optModel,p,*i):

            # Convert the game state to the format of keys of the payoff matrix
            # print("original original i ", i)
            i = self.convert_to_payoffMatrix_key(i)
            # print("original i ", i)

            # All possible responses of P to the action all other players
            # have taken in i
            # print('self.game.payoff_matrix.keys()', self.game.payoff_matrix.keys())
            # print(dict(i))
            # print([dict((('row', 'D'), ('column', 'C')))[pp] == dict(i)[pp] for  pp in dict(i).keys() if pp != p])
            responseP = [k for k in self.game.payoff_matrix.keys() if False not in [dict(k)[pp] == dict(i)[pp] for  pp in dict(i).keys() if pp != p]] 
            # print('responseP', responseP)
            # Find the payoff of the best response of player P 
            bestResP = max([self.game.payoff_matrix[k][p] for k in responseP])

            return self.game.payoff_matrix[i][p] >= bestResP*optModel.y[i] + self.payoffLB*(1 - optModel.y[i])
        
        def add_optlang_NashCond_rule(optlangOptModel,p,i):

            # Convert the game state to the format of keys of the payoff matrix
            # print("optlang i ", i)
            i = self.convert_to_payoffMatrix_key(i)
            # print("otlang new i ", i)
            # print([1,2,3])
            # print(type(*[1,2,3]))

            # All possible responses of P to the action all other players
            # have taken in i
            # print('self.game.payoff_matrix.keys()', self.game.payoff_matrix.keys())
            # print([dict(k)[pp] == dict(i)[pp] for  pp in dict(i).keys() if pp != p])
            
            responseP = [k for k in self.game.payoff_matrix.keys() if False not in [dict(k)[pp] == dict(i)[pp] for  pp in dict(i).keys() if pp != p]]
            # print('optlang responseP', responseP)

            # Find the payoff of the best response of player P 
            bestResP = max([self.game.payoff_matrix[k][p] for k in responseP])
            # print('optlang bestResP', bestResP)
            # print('optlang self.game.payoff_matrix[i][p],', self.game.payoff_matrix[i][p])

            # print(self.game.payoff_matrix[i][p] - bestResP*optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',', '_')] - self.payoffLB*(1 - optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',', '_')]))
            model.add(optlang.Constraint(self.game.payoff_matrix[i][p] - bestResP*optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',','_')] - self.payoffLB*(1 - optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',','_')]), lb=0))
            # return self.game.payoff_matrix[i][p] - bestResP*optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',','_')] - self.payoffLB*(1 - optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',','_')])
        
        # print('NashCond_rule ', NashCond_rule)
        # optModel.P.pprint()
        # optModel.I.pprint()
        optModel.NashCond = Constraint(optModel.P,optModel.I, rule=NashCond_rule)
        optModel.pprint()
        
        #         Key                                   : Lower : Body                                             : Upper : Active
        # ('column', 'row', 'C', 'column', 'C') :  -Inf :                       -6*(1 - y[row,C,column,C]) :  -1.0 :   True
        # ('column', 'row', 'C', 'column', 'D') :  -Inf :                       -6*(1 - y[row,C,column,D]) :   0.0 :   True
        # ('column', 'row', 'D', 'column', 'C') :  -Inf : -3*y[row,D,column,C] - 6*(1 - y[row,D,column,C]) :  -4.0 :   True
        # ('column', 'row', 'D', 'column', 'D') :  -Inf : -3*y[row,D,column,D] - 6*(1 - y[row,D,column,D]) :  -3.0 :   True
        #    ('row', 'row', 'C', 'column', 'C') :  -Inf :                       -6*(1 - y[row,C,column,C]) :  -1.0 :   True
        #    ('row', 'row', 'C', 'column', 'D') :  -Inf : -3*y[row,C,column,D] - 6*(1 - y[row,C,column,D]) :  -4.0 :   True
        #    ('row', 'row', 'D', 'column', 'C') :  -Inf :                       -6*(1 - y[row,D,column,C]) :   0.0 :   True
        #    ('row', 'row', 'D', 'column', 'D') :  -Inf : -3*y[row,D,column,D] - 6*(1 - y[row,D,column,D]) :  -3.0 :   True



        # optModel.NashCond.pprint()
        # print(optlang_NashCond_rule.__str__())
        # for player in players:
        #     for i in optlangInit:
        #         print('player ', player)
        #         print('index ', i)
        #         print(type(i))
        #         optlangOptModel.add(optlang.interface.Constraint(optlang_NashCond_rule(optlangOptModel, player, i), lb=0))
        print("DAISIES")
        model = optlang.Model(name='Original Model')
        model.players = self.game.players_names
        model.indices = [tuple([k3 for k2 in k1 for k3 in k2]) for k1 in self.game.payoff_matrix.keys()]
        
        print(self.game.players_names)
        # model.players = FiniteSet(*self.game.players_names) 
        # model.indices = FiniteSet(*[tuple([k3 for k2 in k1 for k3 in k2]) for k1 in self.game.payoff_matrix.keys()])
        
        print(model.players)
        print(model.indices)
        # optlang.Constraint(optlang_NashCond_rule(model, player, index), lb=0)

        variables_names = []

        # Added all the variables named "p1,c,p2,c" etc.
        for index in model.indices:
            str_index = str(index).replace(" ", "").replace('(', "").replace(')', "").replace("'","")
            var = optlang.Variable(str_index.replace(',', '_'), type='binary', problem=model)
            model.add(var)
            variables_names.append(str_index.replace(',', '_'))

        # Add variables and objective
        # for var in variables_names:
        #     model.add(optlang.Variable(var, type='binary',problem=model))
    
        model.objective = optlang.Objective(expression=sympy.Add(*sympy.symbols(variables_names)), direction='max')

        
        for player in model.players:
            for index in model.indices:
                print('player ', player)
                print('index ', index)
                print(type(index))
                # print(optlang_NashCond_rule(model, player, index))
                add_optlang_NashCond_rule(model, player, index)
        # cons = optlang.Constraint(optlang.Constraint(optlang_NashCond_rule(model, model.players, model.indices), lb=0))
        # print(cons)

        # print('variables_names', variables_names)
        # print('optlang model', model)
        # print('sympy.symbols(variables_names)', sympy.symbols(variables_names))
        # for var in variables_names:
        #     model.add(optlang.Variable(var, type='binary',problem=model))
        # # a = sympy.Add(*sympy.symbols(variables_names))
        # # print(a)
        # expr = sympy.lambdify(sympy.symbols(variables_names), sympy.Add(*sympy.symbols(variables_names)))
        # print(sympy.Add(*sympy.symbols(variables_names)))
        # print('EXPR', expr)
        print('FINAL optlang model', model)
        # model.objective = optlang.Objective(expression=sympy.Add(*sympy.symbols(variables_names)), direction='max')

        self.optModel = optModel 
        # self.optModel = optlangOptModel

    # Elie
    def createOptlangModel(self):
        """
        This creates a optlang optimization model 
        """   
        
        def add_optlang_NashCond_rule(optlangOptModel,p,i):

            # Convert the game state to the format of keys of the payoff matrix
            # print("optlang i ", i)
            i = self.convert_to_payoffMatrix_key(i)
            # print("otlang new i ", i) 
            
            responseP = [k for k in self.game.payoff_matrix.keys() if False not in [dict(k)[pp] == dict(i)[pp] for  pp in dict(i).keys() if pp != p]]
            # print('optlang responseP', responseP)

            # Find the payoff of the best response of player P 
            bestResP = max([self.game.payoff_matrix[k][p] for k in responseP])
            # print('optlang bestResP', bestResP)
            # print('optlang self.game.payoff_matrix[i][p],', self.game.payoff_matrix[i][p])

            # print(self.game.payoff_matrix[i][p] - bestResP*optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',', '_')] - self.payoffLB*(1 - optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',', '_')]))
            model.add(optlang.Constraint(self.game.payoff_matrix[i][p] - bestResP*optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',','_')] - self.payoffLB*(1 - optlangOptModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',','_')]), lb=0))
      
        model = optlang.Model(name='Original Model')
        model.players = self.game.players_names
        model.indices = [tuple([k3 for k2 in k1 for k3 in k2]) for k1 in self.game.payoff_matrix.keys()]
        
        print(self.game.players_names)
        print(model.players)
        print(model.indices)

        variables_names = []

        # Add the variables
        for index in model.indices:
            str_index = str(index).replace(" ", "").replace('(', "").replace(')', "").replace("'","")
            var = optlang.Variable(str_index.replace(',', '_'), type='binary', problem=model)
            model.add(var)
            variables_names.append(str_index.replace(',', '_'))

        # Add the objective function
        model.objective = optlang.Objective(expression=sympy.Add(*sympy.symbols(variables_names)), direction='max')
   
        # Add the constraints
        for player in model.players:
            for index in model.indices:
                # print('player ', player)
                # print('index ', index)
                print(type(index))
                add_optlang_NashCond_rule(model, player, index)

        print('FINAL optlang model', model)
        
        self.optModel = model
    
    
    def findPure(self):
        """ 
        This method runs the optimization problem finding the pure strategy Nash
        equilbirium. 

        OUTPUTS:
        -------
        Nash_equilibria: 
        Is a list containing the labels of the cells of the payoff matrix
        that were found to be a pure strategy Nash equilibrium. For example, in a two-player 
        game if the set of strategies for players 1 and 2 are {s11,s12} and {s21,s22},
        respectively, the optimal values of binary varaibles for each cell can be as follows 
        {('s11','s21'):0,('s11','s21'):1,('s12','s21'):0,('s21','s22'):0}
        and additionally we may have an alternative solution as:
        {('s11','s21'):0,('s11','s21'):0,('s12','s21'):0,('s21','s22'):1}
        Nash_equilibria would be then be a list [('s11','s21'),('s21','s22')] 

        exit_flag: 
        Shows the condition the termination condition of the code (this is different from 
        optimExitflag for solving the optimization problem). exit_flag can take 
        either of the following values:
        - 'objIsZero': The objective function is zero
        - 'solverError': There was an error in both optimization solvers (cplex & guorobi)
        - 'objNotZeroNotOne': An erroneous case where the objective function is neither
                              zero nor one
        - A string showing a non-optimal solution for the optimization problem     
        """
        # Processing and wall time
        # Elie
        # start_run_pt = time.clock()
        start_run_pt = time.process_time()
        start_run_wt = time.time()

        #---- Creating and instantiating the optModel ----
        # Elie
        # start_pyomo_pt = time.clock()
        start_pyomo_pt = time.process_time()
        start_pyomo_wt = time.time()

        # Create the optModel model        
        self.createPyomoModel()

        #---- Solve the model ----
        # Create a solver and set the options
        solverType = pyomoSolverCreator(self.optimization_solver)

        # Elie
        # elapsed_pyomo_pt = str(timedelta(seconds = time.clock() - start_pyomo_pt))
        elapsed_pyomo_pt = str(timedelta(seconds = time.process_time() - start_pyomo_pt))
        elapsed_pyomo_wt = str(timedelta(seconds = time.time() - start_pyomo_wt))

        #-- Some initializations --
        # Instantiate the optModel with new fixed variables
        self.optModel.preprocess()

        #- Solve the optModel (tee=True shows the solver output) -
        try:
            # Elie
            # start_solver_pt = time.clock()
            start_solver_pt = time.process_time()
            start_solver_wt = time.time()

            optSoln = solverType.solve(self.optModel,tee=False)
            solverFlag = 'normal'
    
        # In the case of an error switch the solver
        except:
            if self.warnings:
                print ("WARNING! ",self.optimization_solver," failed. An alternative solver is tried")  
    
            if self.optimization_solver.lower() == 'gurobi':
                self.optimization_solver = 'cplex'
            elif self.optimization_solver.lower() == 'cplex':
                self.optimization_solver = 'gurobi'
    
            # Try solving with the alternative solver
            solverType = pyomoSolverCreator(self.optimization_solver)
            try:
                # Elie
                # start_solver_pt = time.clock()
                start_solver_pt = time.process_time()
                start_solver_wt = time.time()

                optSoln = solverType.solve(self.optModel,tee=False)
                solverFlag = 'normal'
            except:
                solverFlag = 'solverError'
                if self.warnings:
                    print ('\nWARNING! The alternative solver failed. No solution was returned')
        # Elie
        # elapsed_solver_pt = str(timedelta(seconds = time.clock() - start_solver_pt))
        elapsed_solver_pt = str(timedelta(seconds = time.process_time() - start_solver_pt))
        elapsed_solver_wt = str(timedelta(seconds = time.time() - start_solver_wt))
    
        #----- Print the results in the output (screen, file and/or variable) ------
        # Load the results (model.load() is dprecated)
        #self.optModel.load(optSoln)
            
        # Set of the Nash equilibria
        self.Nash_equilibria = []
        
        if solverFlag == 'normal' and str(optSoln.solver.termination_condition).lower() == 'optimal':
            
            optimExitflag = 'globallyOptimal'
    
            # Value of the objective function
            objValue = self.optModel.objective_rule()
    
            # Print the results on the screen 
            if self.stdout_msgs:
                print ("\nsolver.status = ",optSoln.solver.termination_condition,"\n")
                print ("objective value = ",objValue)

            if objValue >= 1:
                self.exit_flag = 'objGreaterThanZero'
                for i in self.optModel.I.value: 
                    if self.optModel.y[i].value == 1:
                        self.Nash_equilibria.append(list(self.convert_to_payoffMatrix_key(i)))
            elif objValue == 0:
                done = 1
                self.exit_flag = 'objIsZero'
                      
            # Write the results into the output file 
            if self.output_file != '': 
                pass   # To be added 

        # If the optimization problem was not solved successfully
        else:

            if solverFlag == 'solverError':
                optimExitflag = solverFlag
                self.exit_flag = solverFlag
            else:
                optimExitflag = str(optSoln.solver.termination_condition)
                self.exit_flag = str(optSoln.solver.termination_condition)
 
            objValue = None 
    
            # Write on the screen
            if self.warnings:
                print ("\nWARNING! No optimal solutions found (solution.solver.status = ",optSoln.Solution.status,", solver.status =",optSoln.solver.status,", solver.termination_condition = ",optSoln.solver.termination_condition,")\n")
    
            # Write the results into the output file
            if self.output_file != None: 
                pass    # *** To be completed ***
            else:
                pass
    
        # Time required to run 
        # Elie
        # elapsed_run_pt = str(timedelta(seconds = time.clock() - start_run_pt))
        elapsed_run_pt = str(timedelta(seconds = time.process_time() - start_run_pt))
        elapsed_run_wt = str(timedelta(seconds = time.time() - start_run_wt))
    
        if self.stdout_msgs:
           print ('NashEqFinder took (hh:mm:ss) (processing/wall) time: pyomo = {}/{}  ,  solver = {}/{}  ,  run = {}/{} for a game with {} cells in its payoff matrix\n'.format(elapsed_pyomo_pt,elapsed_pyomo_wt,elapsed_solver_pt,elapsed_solver_wt,elapsed_run_pt,elapsed_run_wt, len(self.game.payoff_matrix)) )

    

    # Elie
    def optlangFindPure(self):
        """ 
        This method runs the optimization problem finding the pure strategy Nash
        equilbirium. 

        OUTPUTS:
        -------
        Nash_equilibria: 
        Is a list containing the labels of the cells of the payoff matrix
        that were found to be a pure strategy Nash equilibrium. For example, in a two-player 
        game if the set of strategies for players 1 and 2 are {s11,s12} and {s21,s22},
        respectively, the optimal values of binary varaibles for each cell can be as follows 
        {('s11','s21'):0,('s11','s21'):1,('s12','s21'):0,('s21','s22'):0}
        and additionally we may have an alternative solution as:
        {('s11','s21'):0,('s11','s21'):0,('s12','s21'):0,('s21','s22'):1}
        Nash_equilibria would be then be a list [('s11','s21'),('s21','s22')] 

        exit_flag: 
        Shows the condition the termination condition of the code (this is different from 
        optimExitflag for solving the optimization problem). exit_flag can take 
        either of the following values:
        - 'objIsZero': The objective function is zero
        - 'solverError': There was an error in both optimization solvers (cplex & guorobi)
        - 'objNotZeroNotOne': An erroneous case where the objective function is neither
                              zero nor one
        - A string showing a non-optimal solution for the optimization problem     
        """
        # Processing and wall time
        # Elie
        # start_run_pt = time.clock()
        start_run_pt = time.process_time()
        start_run_wt = time.time()

        #---- Creating and instantiating the optModel ----
        # Elie
        # start_pyomo_pt = time.clock()
        start_optlang_pt = time.process_time()
        start_optlang_wt = time.time()

        # Create the optModel model        
        self.createOptlangModel()

        #---- Solve the model ----
        # Create a solver and set the options
        # solverType = pyomoSolverCreator(self.optimization_solver)

        # Elie
        # elapsed_pyomo_pt = str(timedelta(seconds = time.clock() - start_pyomo_pt))
        elapsed_optlang_pt = str(timedelta(seconds = time.process_time() - start_optlang_pt))
        elapsed_optlang_wt = str(timedelta(seconds = time.time() - start_optlang_wt))

        #-- Some initializations --
        # Instantiate the optModel with new fixed variables
        # self.optModel.preprocess()

        #- Solve the optModel
        # Elie
        # start_solver_pt = time.clock()
        start_solver_pt = time.process_time()
        start_solver_wt = time.time()

        # optSoln = solverType.solve(self.optModel,tee=False)
        optSoln = self.optModel.optimize()

        # Print the results on the screen 
        print("status:", self.optModel.status)
        print("objective value:", self.optModel.objective.value)
        print("----------")
        for var_name, var in self.optModel.variables.items():
            print(var_name, "=", var.primal)
        solverFlag = 'normal'
    
        # Elie
        # elapsed_solver_pt = str(timedelta(seconds = time.clock() - start_solver_pt))
        elapsed_solver_pt = str(timedelta(seconds = time.process_time() - start_solver_pt))
        elapsed_solver_wt = str(timedelta(seconds = time.time() - start_solver_wt))
    
        #----- Print the results in the output (screen, file and/or variable) ------
        # Load the results (model.load() is dprecated)
        #self.optModel.load(optSoln)
            
        # Set of the Nash equilibria
        self.Nash_equilibria = []
        objValue = self.optModel.objective.value
        if objValue >= 1:
            self.exit_flag = 'objGreaterThanZero'
            for i in self.optModel.indices: 
                if self.optModel.variables[str(i).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',', '_')].primal == 1:
                    self.Nash_equilibria.append(list(self.convert_to_payoffMatrix_key(i)))
        elif objValue == 0:
            done = 1
            self.exit_flag = 'objIsZero'
    
        # Time required to run 
        # Elie
        # elapsed_run_pt = str(timedelta(seconds = time.clock() - start_run_pt))
        elapsed_run_pt = str(timedelta(seconds = time.process_time() - start_run_pt))
        elapsed_run_wt = str(timedelta(seconds = time.time() - start_run_wt))
    
        if self.stdout_msgs:
           print ('NashEqFinder took (hh:mm:ss) (processing/wall) time: pyomo = {}/{}  ,  solver = {}/{}  ,  run = {}/{} for a game with {} cells in its payoff matrix\n'.format(elapsed_optlang_pt,elapsed_optlang_wt,elapsed_solver_pt,elapsed_solver_wt,elapsed_run_pt,elapsed_run_wt, len(self.game.payoff_matrix)) )
    
    def run(self):
        """
        Runs the Nash equilibrium finder
        """
        if self.NashEq_type.lower() == 'pure':
            self.findPure()
        elif self.NashEq_type.lower() == 'mixed':
            pass # To be completed

        return [self.Nash_equilibria,self.exit_flag]

    
    # Elie
    def optlangRun(self):
        """
        Runs the Nash equilibrium finder
        """
        if self.NashEq_type.lower() == 'pure':
            self.optlangFindPure()
        elif self.NashEq_type.lower() == 'mixed':
            pass # To be completed

        return [self.Nash_equilibria,self.exit_flag]

    # Elie
    def validate(self, nasheq_cells):
        # Validation: needs removal of hard coded methods
        print("\n Validation \n")
        def string_to_index(string):
            lst = string.split('_')
            player = lst[-2]
            sign = lst[-1]
            return (((lst[0],lst[1]), (lst[2],lst[3]))), player, sign

        original_payoff_matrix = copy.deepcopy(self.game.payoff_matrix)

        for var_name, var in self.optModel.variables.items():
            print(var_name, "=", var.primal)
            matrix_key, player, sign = string_to_index(var_name)
            if sign == 'plus':
                self.game.payoff_matrix[matrix_key][player] += var.primal
            if sign == 'minus':
                self.game.payoff_matrix[matrix_key][player] -= var.primal
        #     perturbation = \
        #             (self.optModel.variables[current_index + '_' + player + '_' + 'plus'][1].primal()
        #             -self.optModel.variables[current_index + '_' + player + '_' + 'minus'][1].primal())
            
        #     print(var_name, "=", var.primal)

        # for key in self.game.payoff_matrix.keys():
        #     current_index = strip_down(key)
        #     for player in model.players:
        #         print(self.optModel.variables[current_index + '_' + player + '_' + 'plus'])
        #         perturbation = \
        #             (self.optModel.variables[current_index + '_' + player + '_' + 'plus'][1].primal()
        #             -self.optModel.variables[current_index + '_' + player + '_' + 'minus'][1].primal())
        #         self.game.payoff_matrix[key][player] += perturbation

        print('New payoff matrix', self.game.payoff_matrix)

        # self.game.payoff_matrix = original_payoff_matrix

        # print('Original payoff matrix', self.game.payoff_matrix)
        
        # # Define an instance of the game
        # new_game = game(game_name, players_names, players_strategies, payoff_matrix)
        
        # Define an instance of the NashEqFinder
        NashEqFinderInst = NashEqFinder(self.game, stdout_msgs = True)
        [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
        [Nash_equilibria,exit_flag] = NashEqFinderInst.optlangRun()

        print("DONE")
        
        print ('exit_flag = ',exit_flag)
        print ('Nash_equilibria = ',Nash_equilibria )
        for desired_state in nasheq_cells:
            if list(desired_state) in Nash_equilibria:
                print('DESIRED STATE', desired_state, "ACHIEVED with these perturbations")
                for var_name, var in self.optModel.variables.items():
                    print(var_name, "=", var.primal)
            else:
                print('DESIRED STATE', desired_state, "FAILED")
                for var_name, var in self.optModel.variables.items():
                    print(var_name, "=", var.primal)

    # Elie
    def newEquilibria(self, nasheq_cells, strategies):
        """
        :param nasheq_cells: a list of elements (('row','C'),('column','C'))

        Consider a payoff value a. We would like to perturb it such that it can
        either increase or decrease. To do this, we define two non-negative 
        variables aa^+ and aa^-. Then we change the payoff as follows:

                                    β=a+aa^+-aa^-

        As the objective function then, you minimize sum of all aa^+'s and 
        aa^-'s for all payoff. 

        """   

        # Adding new variables

      
        model = optlang.Model(name='Original Model')
        model.players = self.game.players_names
        indices = [tuple([k3 for k2 in k1 for k3 in k2]) for k1 in self.game.payoff_matrix.keys()]
        new_indices = []
        for index in indices:
            for player in model.players:
                new_indices.append(index + (player, 'plus'))
                new_indices.append(index + (player, 'minus'))
                # new_indices.append(index + ('plus2',))
                # new_indices.append(index + ('minus2',))
        # Format of indices: e.g. ('row','C','column','C','row','plus')
        model.indices = new_indices
        


        # print(self.game.players_names)
        # print(model.players)
        # print(model.indices)

        variables_names = []

        # Add the variables
        for index in model.indices:
            str_index = str(index).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',', '_')
            var = optlang.Variable(str_index, lb=0, type='continuous', problem=model)
            model.add(var)
            variables_names.append(str_index)

        # Add the objective function
        model.objective = optlang.Objective(expression=sympy.Add(*sympy.symbols(variables_names)), direction='min')
   
        def strip_down(index):
            return str(index).replace(" ", "").replace('(', "").replace(')', "").replace("'","").replace(',', '_')

        # Add the constraints
        constraints = []
        # Each `cell` is of the format (('row','C'),('column','C'))
        for cell in nasheq_cells:
            
            strategies
            root_index = strip_down(cell)
            # print('original cell', cell)
            # print('root_index', root_index)
            
            # add_optlang_NashCond_rule(model, player, index)
            # matrix_key = cell[0] + cell[1]
            # [[k3 for k2 in k1 for k3 in k2]) for k1 in self.game.payoff_matrix.keys()]

            # For first player we loop over first axis (rows=strategies)
            for strategy in [x for x in strategies if x != cell[0][1]]:
                current_cell = ((cell[0][0], strategy), (cell[1]))
                current_index = strip_down(current_cell)
                # print('current_index ', current_index)
                # print('current_cell', current_cell)
                player = model.players[0]
                # print('root strategy payoff', self.game.payoff_matrix[cell][player])
                # print('current strategy payoff', self.game.payoff_matrix[current_cell][player]) 
                c = optlang.Constraint(
                        self.game.payoff_matrix[cell][player] \
                        + model.variables[root_index+'_'+player+'_plus'] \
                        - model.variables[root_index+'_'+player+'_minus'] \
                        - 
                        (self.game.payoff_matrix[current_cell][player] \
                        + model.variables[current_index+'_'+player+'_plus'] \
                        - model.variables[current_index+'_'+player+'_minus']
                        ), lb=0)
                # print('c', c)
                constraints.append(c)
            print("ADDED rows loop")

            for strategy in [x for x in strategies if x != cell[1][1]]:
                current_cell = ((cell[0]), (cell[1][0], strategy))
                current_index = strip_down(current_cell)
                # print('current_index ', current_index)
                # print('current_cell', current_cell)
                player = model.players[1]
                # print('root strategy payoff', self.game.payoff_matrix[cell][player])
                # print('current strategy payoff', self.game.payoff_matrix[current_cell][player])
                c = optlang.Constraint(
                        self.game.payoff_matrix[cell][player] \
                        + model.variables[root_index+'_'+player+'_plus'] \
                        - model.variables[root_index+'_'+player+'_minus'] \
                        - 
                        (self.game.payoff_matrix[current_cell][player] \
                        + model.variables[current_index+'_'+player+'_plus'] \
                        - model.variables[current_index+'_'+player+'_minus']
                        ), lb=0)
                # print('c', c)
                constraints.append(c)
            print("ADDED columns loop")
        
        print(constraints)
        model.add(constraints)        
        self.optModel = model        
        self.optModel.optimize()

        print('FINAL optlang model', model)

        # Print the results on the screen 
        print("status:", self.optModel.status)
        print("objective value:", self.optModel.objective.value)
        print("----------")
        for var_name, var in self.optModel.variables.items():
            print(var_name, "=", var.primal)

        original_payoff_matrix = copy.deepcopy(self.game.payoff_matrix)

        self.validate(nasheq_cells)
        # # Validation: needs removal of hard coded methods
        # print("\n Validation \n")
        # def string_to_index(string):
        #     lst = string.split('_')
        #     player = lst[-2]
        #     sign = lst[-1]
        #     return (((lst[0],lst[1]), (lst[2],lst[3]))), player, sign

        # original_payoff_matrix = copy.deepcopy(self.game.payoff_matrix)

        # for var_name, var in self.optModel.variables.items():
        #     print(var_name, "=", var.primal)
        #     matrix_key, player, sign = string_to_index(var_name)
        #     if sign == 'plus':
        #         self.game.payoff_matrix[matrix_key][player] += var.primal
        #     if sign == 'minus':
        #         self.game.payoff_matrix[matrix_key][player] -= var.primal
        # #     perturbation = \
        # #             (self.optModel.variables[current_index + '_' + player + '_' + 'plus'][1].primal()
        # #             -self.optModel.variables[current_index + '_' + player + '_' + 'minus'][1].primal())
            
        # #     print(var_name, "=", var.primal)

        # # for key in self.game.payoff_matrix.keys():
        # #     current_index = strip_down(key)
        # #     for player in model.players:
        # #         print(self.optModel.variables[current_index + '_' + player + '_' + 'plus'])
        # #         perturbation = \
        # #             (self.optModel.variables[current_index + '_' + player + '_' + 'plus'][1].primal()
        # #             -self.optModel.variables[current_index + '_' + player + '_' + 'minus'][1].primal())
        # #         self.game.payoff_matrix[key][player] += perturbation

        # print('New payoff matrix', self.game.payoff_matrix)

        self.game.payoff_matrix = original_payoff_matrix

        print('Original payoff matrix', self.game.payoff_matrix)
        
        # # Define an instance of the game
        # new_game = game(game_name, players_names, players_strategies, payoff_matrix)
        
        # # Define an instance of the NashEqFinder
        # NashEqFinderInst = NashEqFinder(new_game, stdout_msgs = True)
        # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
        # [Nash_equilibria,exit_flag] = NashEqFinderInst.optlangRun()

        # print("DONE")
        
        # print ('exit_flag = ',exit_flag)
        # print ('Nash_equilibria = ',Nash_equilibria )

        print("\n Fixing all nonzero alphas \n")
        # Fix all α's that were non-zero in the current solution at zero, so 
        # those payoffs are not part of the future solutions at all.
        nonzero_vars = []
        for var_name, var in self.optModel.variables.items():
            if var.primal > 0:
                nonzero_vars.append(var_name)
                # Setting the variable to zero
                c = optlang.Constraint(model.variables[var_name], lb=0, ub=0)
                constraints.append(c)
                model.add(c) 

        print(constraints)
        
        self.optModel = model        
        self.optModel.optimize()

        print('FINAL optlang model', model)

        # Print the results on the screen 
        print("status:", self.optModel.status)
        print("objective value:", self.optModel.objective.value)
        print("----------")
        for var_name, var in self.optModel.variables.items():
            print(var_name, "=", var.primal)

        original_payoff_matrix = copy.deepcopy(self.game.payoff_matrix)
        self.validate(nasheq_cells)
        self.game.payoff_matrix = original_payoff_matrix
        print('Original payoff matrix', self.game.payoff_matrix)


        # print("\n Preventing alphas from being their optimal value \n")
        # # For each non-zero α whose optimal value is α^opt, add the following
        # # constraints:
        # #                       α≤α^opt-ϵ  &  α≥ α^opt+ϵ
        # # Where, ϵ is a parameter provided by the user. We should try both 
        # # small (e.g., 0.01) and large (e.g., 0.5) values. For example, if 
        # # α^opt=1, examine the following values for ϵ=[0.1,0.2,…,0.9]

        # for var_name, var in self.optModel.variables.items():
        #     # Setting the variable to zero
        #     c = optlang.Constraint(model.variables[var_name], lb=0, ub=0)
        #     model.add(c) 
        
        # self.optModel = model        
        # self.optModel.optimize()

        # print('FINAL optlang model', model)

        # # Print the results on the screen 
        # print("status:", self.optModel.status)
        # print("objective value:", self.optModel.objective.value)
        # print("----------")
        # for var_name, var in self.optModel.variables.items():
        #     print(var_name, "=", var.primal)

        # original_payoff_matrix = copy.deepcopy(self.game.payoff_matrix)
        # self.validate(nasheq_cells)
        # self.game.payoff_matrix = original_payoff_matrix
        # print('Original payoff matrix', self.game.payoff_matrix)

    
        

#--------- Sample implementation ------
if __name__ == "__main__":

    from game import *
    print ("\n\n\n\n\n\n\n\n\n\n")
    
    #---------------------------------- 
    print ("\n-- Prisoner's Dilemma ---")
    # Pure strategy Nash eq = (D,D)
    
    game_name = "Prisoner's Dilemma"
    numberOfPlayers = 2
    players_names = ['row','column']
    
    players_strategies = {}
    players_strategies['row'] = ['C','D']
    players_strategies['column'] = ['C','D']
    
    payoff_matrix = {}
    payoff_matrix[(('row','C'),('column','C'))] = {'row':-1,'column':-1}
    payoff_matrix[(('row','C'),('column','D'))] = {'row':-4,'column':0}
    payoff_matrix[(('row','D'),('column','C'))] = {'row':0,'column':-4}
    payoff_matrix[(('row','D'),('column','D'))] = {'row':-3,'column':-3}
    
    # Define an instance of the game
    PD = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # Define an instance of the NashEqFinder
    NashEqFinderInst = NashEqFinder(PD, stdout_msgs = True)
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.optlangRun()
    NashEqFinderInst.newEquilibria(nasheq_cells=[(('row','C'),('column','D'))], strategies=['C', 'D'])

    # # Validation:
    # payoff_matrix = {}
    # payoff_matrix[(('row','C'),('column','C'))] = {'row':-1,'column':-1}
    # payoff_matrix[(('row','C'),('column','D'))] = {'row':-4 + 1,'column':0} #validation
    # payoff_matrix[(('row','D'),('column','C'))] = {'row':0,'column':-4}
    # payoff_matrix[(('row','D'),('column','D'))] = {'row':-3,'column':-3}
    
    # # Define an instance of the game
    # PD = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(PD, stdout_msgs = True)
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.optlangRun()

    # print("DONE")
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )
    
    # #---------------------------------- 
    # print ("\n-- Game of pure coordination ---")
    # # Pure strategy Nash eq: (Left,Left) and (Right,Right)
    
    # game_name = "Pure coordination"
    # numberOfPlayers = 2
    # players_names = ['row','column']
    
    # players_strategies = {}
    # players_strategies['row'] = ['Left','Right']
    # players_strategies['column'] = ['Left','Right']
    
    # payoff_matrix = {}
    # payoff_matrix[(('row','Left'),('column','Left'))] = {'row':1,'column':1}
    # payoff_matrix[(('row','Left'),('column','Right'))] = {'row':0,'column':0}
    # payoff_matrix[(('row','Right'),('column','Left'))] = {'row':0,'column':0}
    # payoff_matrix[(('row','Right'),('column','Right'))] = {'row':1,'column':1}
    
    # # Define an instance of the game
    # PC = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(PC, stdout_msgs = True)
    # # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.optlangRun()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )
    
    # #---------------------------------- 
    # print ("\n-- Game of Battle of the sexes ---")
    # # Pure strategy Nash eq: (B,B) and (F,F)
    
    # game_name = "Battle of the sexes"
    # numberOfPlayers = 2
    # players_names = ['husband','wife']
    
    # players_strategies = {}
    # players_strategies['husband'] = ['B','F']
    # players_strategies['wife'] = ['B','F']
    
    # payoff_matrix = {}
    # payoff_matrix[(('husband','B'),('wife','B'))] = {'husband':2,'wife':1}
    # payoff_matrix[(('husband','B'),('wife','F'))] = {'husband':0,'wife':0}
    # payoff_matrix[(('husband','F'),('wife','B'))] = {'husband':0,'wife':0}
    # payoff_matrix[(('husband','F'),('wife','F'))] = {'husband':1,'wife':2}
    
    # # Define an instance of the game
    # BS = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(BS, stdout_msgs = True)
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )
    
    # #---------------------------------- 
    # print ("\n-- Game of Matching pennies ---")
    # # Pure strategy Nash eq: None
    
    # game_name = "Matching pennies"
    # numberOfPlayers = 2
    # players_names = ['row','column']
    
    # players_strategies = {}
    # players_strategies['row'] = ['Heads','Tails']
    # players_strategies['column'] = ['Heads','Tails']
    
    # payoff_matrix = {}
    # payoff_matrix[(('row','Heads'),('column','Heads'))] = {'row':1,'column':-1}
    # payoff_matrix[(('row','Heads'),('column','Tails'))] = {'row':-1,'column':1}
    # payoff_matrix[(('row','Tails'),('column','Heads'))] = {'row':-1,'column':1}
    # payoff_matrix[(('row','Tails'),('column','Tails'))] = {'row':1,'column':-1}
    
    # # Define an instance of the game
    # MP = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(MP, stdout_msgs = True)
    # [Nash_equilibria,exit_flag]  = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )
    
    # #---------------------------------- 
    # print ("\n-- Problem 4- Homework 1 (game theory I) ---")
    # # This is a game with two players and multiple strategies
    # # Pure strategy Nash eq: (c,y)
    # game_name = "Hw1Prob4"
    # numberOfPlayers = 2
    # players_names = ['row','column']
    
    # players_strategies = {}
    # players_strategies['row'] = ['a','b','c','d']
    # players_strategies['column'] = ['x','y','z']
    
    # payoff_matrix = {}
    # payoff_matrix[(('row','a'),('column','x'))] = {'row':1,'column':2}
    # payoff_matrix[(('row','a'),('column','y'))] = {'row':2,'column':2}
    # payoff_matrix[(('row','a'),('column','z'))] = {'row':5,'column':1}
    
    # payoff_matrix[(('row','b'),('column','x'))] = {'row':4,'column':1}
    # payoff_matrix[(('row','b'),('column','y'))] = {'row':3,'column':5}
    # payoff_matrix[(('row','b'),('column','z'))] = {'row':3,'column':3}
    
    # payoff_matrix[(('row','c'),('column','x'))] = {'row':5,'column':2}
    # payoff_matrix[(('row','c'),('column','y'))] = {'row':4,'column':4}
    # payoff_matrix[(('row','c'),('column','z'))] = {'row':7,'column':0}
    
    # payoff_matrix[(('row','d'),('column','x'))] = {'row':2,'column':3}
    # payoff_matrix[(('row','d'),('column','y'))] = {'row':0,'column':4}
    # payoff_matrix[(('row','d'),('column','z'))] = {'row':3,'column':0}
    
    # # Define an instance of the game
    # Hw1Pb4 = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(Hw1Pb4, stdout_msgs = True)
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )
    
    
    # #---------------------------------- 
    # print ("\n-- Problem 9- Homework 1 (game theory I) ---")
    # # This is a game with three players and two strategies
    # # Pure strategy Nash eq: (c,y)
    
    # game_name = "Pure coordination"
    # numberOfPlayers = 3
    # players_names = ['voter1','voter2','voter3']
    
    # players_strategies = {}
    # players_strategies['voter1'] = ['candidateA','candidateB']
    # players_strategies['voter2'] = ['candidateA','candidateB']
    # players_strategies['voter3'] = ['candidateA','candidateB']
    
    # payoff_matrix = {}
    # payoff_matrix[(('voter1','candidateA'),('voter2','candidateA'),('voter3','candidateA'))] = {'voter1':1,'voter2':0,'voter3':0}
    # payoff_matrix[(('voter1','candidateA'),('voter2','candidateA'),('voter3','candidateB'))] = {'voter1':1,'voter2':0,'voter3':0}
    # payoff_matrix[(('voter1','candidateA'),('voter2','candidateB'),('voter3','candidateA'))] = {'voter1':1,'voter2':0,'voter3':0}
    # payoff_matrix[(('voter1','candidateA'),('voter2','candidateB'),('voter3','candidateB'))] = {'voter1':0,'voter2':1,'voter3':1}
    # payoff_matrix[(('voter1','candidateB'),('voter2','candidateA'),('voter3','candidateA'))] = {'voter1':1,'voter2':0,'voter3':0}
    # payoff_matrix[(('voter1','candidateB'),('voter2','candidateA'),('voter3','candidateB'))] = {'voter1':0,'voter2':1,'voter3':1}
    # payoff_matrix[(('voter1','candidateB'),('voter2','candidateB'),('voter3','candidateA'))] = {'voter1':0,'voter2':1,'voter3':1}
    # payoff_matrix[(('voter1','candidateB'),('voter2','candidateB'),('voter3','candidateB'))] = {'voter1':0,'voter2':1,'voter3':1}
    
    # # Define an instance of the game
    # Hw1Pb9 = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(Hw1Pb9, stdout_msgs = True)
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )

    # #---------------------------------- 
    # print ("\n-- Mutualism 1 ---")
    # # Pure strategy Nash eq: None
    
    # game_name = "Mutualism"
    # numberOfPlayers = 2
    # players_names = ['m1','m2']
    
    # players_strategies = {}
    # players_strategies['m1'] = ['C','D']
    # players_strategies['m2'] = ['C','D']
    
    # payoff_matrix = {}
    # payoff_matrix[(('m1','C'),('m2','C'))] = {'m1':5,'m2':6}
    # payoff_matrix[(('m1','C'),('m2','D'))] = {'m1':-1,'m2':8}
    # payoff_matrix[(('m1','D'),('m2','C'))] = {'m1':7,'m2':-2}
    # payoff_matrix[(('m1','D'),('m2','D'))] = {'m1':0,'m2':0}
    
    # # Define an instance of the game
    # MP = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(MP, stdout_msgs = True)
    # [Nash_equilibria,exit_flag]  = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )

    # #---------------------------------- 
    # print ("\n-- Mutualism 2 ---")
    # # Pure strategy Nash eq: None
    
    # game_name = "Mutualism"
    # numberOfPlayers = 2
    # players_names = ['p1','p2']
    
    # players_strategies = {}
    # players_strategies['p1'] = ['C1','C2','D1','D2']
    # players_strategies['p2'] = ['C1','C2','D1','D2']
    
    # payoff_matrix = {}
    # payoff_matrix[(('p1','C1'),('p2','C1'))] = {'p1':0,'p2':0}
    # payoff_matrix[(('p1','C1'),('p2','D1'))] = {'p1':0,'p2':0}
    # payoff_matrix[(('p1','C1'),('p2','C2'))] = {'p1':5,'p2':3}
    # payoff_matrix[(('p1','C1'),('p2','D2'))] = {'p1':-1,'p2':8}

    # payoff_matrix[(('p1','D1'),('p2','C1'))] = {'p1':0,'p2':0}
    # payoff_matrix[(('p1','D1'),('p2','D1'))] = {'p1':0,'p2':0}
    # payoff_matrix[(('p1','D1'),('p2','C2'))] = {'p1':7,'p2':-2}
    # payoff_matrix[(('p1','D1'),('p2','D2'))] = {'p1':0,'p2':0}

    # payoff_matrix[(('p1','C2'),('p2','C1'))] = {'p1':3,'p2':5}
    # payoff_matrix[(('p1','C2'),('p2','D1'))] = {'p1':-2,'p2':7}
    # payoff_matrix[(('p1','C2'),('p2','C2'))] = {'p1':0,'p2':0}
    # payoff_matrix[(('p1','C2'),('p2','D2'))] = {'p1':0,'p2':0}

    # payoff_matrix[(('p1','D2'),('p2','C1'))] = {'p1':8,'p2':-1}
    # payoff_matrix[(('p1','D2'),('p2','D1'))] = {'p1':0,'p2':0}
    # payoff_matrix[(('p1','D2'),('p2','C2'))] = {'p1':0,'p2':0}
    # payoff_matrix[(('p1','D2'),('p2','D2'))] = {'p1':0,'p2':0}
    
    # # Define an instance of the game
    # MP = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(MP, stdout_msgs = True)
    # [Nash_equilibria,exit_flag]  = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )


    # #---------------------------------- 
    # print ("\n-- Synergism ---")
    # # Pure strategy Nash eq: None
    
    # game_name = "Synergism"
    # numberOfPlayers = 2
    # players_names = ['m1','m2']
    
    # players_strategies = {}
    # players_strategies['m1'] = ['C','D']
    # players_strategies['m2'] = ['C','D']
    
    # payoff_matrix = {}
    # payoff_matrix[(('m1','C'),('m2','C'))] = {'m1':5,'m2':6}
    # payoff_matrix[(('m1','C'),('m2','D'))] = {'m1':1,'m2':6}
    # payoff_matrix[(('m1','D'),('m2','C'))] = {'m1':5,'m2':2}
    # payoff_matrix[(('m1','D'),('m2','D'))] = {'m1':1,'m2':2}
    
    # # Define an instance of the game
    # MP = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(MP, stdout_msgs = True)
    # [Nash_equilibria,exit_flag]  = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )

    # #---------------------------------- 
    # print ("\n-- Commensalism ---")
    # # Pure strategy Nash eq: None
    
    # game_name = "Commensalism"
    # numberOfPlayers = 2
    # players_names = ['m1','m2']
    
    # players_strategies = {}
    # players_strategies['m1'] = ['C','D']
    # players_strategies['m2'] = ['D']
    
    # payoff_matrix = {}
    # payoff_matrix[(('m1','C'),('m2','D'))] = {'m1':5,'m2':6}
    # payoff_matrix[(('m1','D'),('m2','D'))] = {'m1':5,'m2':2}
    
    # # Define an instance of the game
    # MP = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(MP, stdout_msgs = True)
    # [Nash_equilibria,exit_flag]  = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )

    
    # #---------------------------------- 
    # print ("\n-- Maya's game (e = 0.8 sATP = 5) --> Mutually Beneficial ---")
    
    # game_name = "Maya's game: e = 0.8 sATP = 5"
    # numberOfPlayers = 2
    # players_names = ['row','column']
    
    # players_strategies = {}
    # players_strategies['row'] = ['C','D']
    # players_strategies['column'] = ['C','D']
    
    # payoff_matrix = {}
    # payoff_matrix[(('row','C'),('column','C'))] = {'row':0.044,'column':0.044}
    # payoff_matrix[(('row','C'),('column','D'))] = {'row':0.039,'column':0.008}
    # payoff_matrix[(('row','D'),('column','C'))] = {'row':0.008,'column':0.039}
    # payoff_matrix[(('row','D'),('column','D'))] = {'row':-0.0016,'column':-0.0016}
    
    # # Define an instance of the game
    # PD = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(PD, stdout_msgs = True)
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )
    
    # #---------------------------------- 
    # print ("\n-- Maya's game (e = 0.01 sATP = 5) --> Prisoner's Dilemma ---")
    
    # game_name = "Maya's game: e = 0.01 sATP = 5"
    # numberOfPlayers = 2
    # players_names = ['row','column']
    
    # players_strategies = {}
    # players_strategies['row'] = ['C','D']
    # players_strategies['column'] = ['C','D']
    
    # payoff_matrix = {}
    # payoff_matrix[(('row','C'),('column','C'))] = {'row':0.28,'column':0.28}
    # payoff_matrix[(('row','C'),('column','D'))] = {'row':0.0011,'column':0.27}
    # payoff_matrix[(('row','D'),('column','C'))] = {'row':0.27,'column':0.0011}
    # payoff_matrix[(('row','D'),('column','D'))] = {'row':-0.0016,'column':-0.0016}
    
    # # Define an instance of the game
    # PD = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(PD, stdout_msgs = True)
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )

    # #---------------------------------- 
    # print ("\n-- Maya's game (e = 0.4 sATP = 5) - Snowdirft ---")
    
    # game_name = "Maya's game: e = 0.8 sATP = 5"
    # numberOfPlayers = 2
    # players_names = ['row','column']
    
    # players_strategies = {}
    # players_strategies['row'] = ['C','D']
    # players_strategies['column'] = ['C','D']
    
    # payoff_matrix = {}
    # payoff_matrix[(('row','C'),('column','C'))] = {'row':0.063,'column':0.063}
    # payoff_matrix[(('row','C'),('column','D'))] = {'row':0.022,'column':0.060}
    # payoff_matrix[(('row','D'),('column','C'))] = {'row':0.060,'column':0.022}
    # payoff_matrix[(('row','D'),('column','D'))] = {'row':-0.0016,'column':-0.0016}
    
    # # Define an instance of the game
    # PD = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(PD, stdout_msgs = True)
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )

    # #---------------------------------- 
    # print ("\n-- Elie's game (e = 0.01 sATP = 5) --> Prisoner's Dilemma ---")
    
    # game_name = "Elie's game: e = 0.01 sATP = 5"
    # numberOfPlayers = 2
    # players_names = ['row','column']
    
    # players_strategies = {}
    # players_strategies['row'] = ['C','D']
    # players_strategies['column'] = ['C','D']
    
    # payoff_matrix = {}
    # payoff_matrix[(('row','C'),('column','C'))] = {'row':0.28,'column':0.28}
    # payoff_matrix[(('row','C'),('column','D'))] = {'row':0.0011,'column':0.27}
    # payoff_matrix[(('row','D'),('column','C'))] = {'row':0.27,'column':0.0011}
    # payoff_matrix[(('row','D'),('column','D'))] = {'row':-0.0016,'column':-0.0016}
    
    # # Define an instance of the game
    # PD = game(game_name, players_names, players_strategies, payoff_matrix)
    
    # # Define an instance of the NashEqFinder
    # NashEqFinderInst = NashEqFinder(PD, stdout_msgs = True)
    # [Nash_equilibria,exit_flag] = NashEqFinderInst.run()
    
    # print ('exit_flag = ',exit_flag)
    # print ('Nash_equilibria = ',Nash_equilibria )


