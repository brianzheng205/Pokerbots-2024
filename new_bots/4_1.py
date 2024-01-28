from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, BidAction
from skeleton.states import GameState, TerminalState, RoundState
from skeleton.states import NUM_ROUNDS, STARTING_STACK, BIG_BLIND, SMALL_BLIND
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot
import random
import eval7
import math


class Player(Bot):
    '''
    A pokerbot.
    '''

    def __init__(self):
        '''
        Called when a new game starts. Called exactly once.

        Arguments:
        Nothing.

        Returns:
        Nothing.
        '''
        self.MONTE_CARLO_ITERS = 200
        self.rounds_fold_to_raise = 0
        self.PROB_THRESHOLD = 0.6

    def handle_new_round(self, game_state, round_state, active):
        '''
        Called when a new round starts. Called NUM_ROUNDS times.

        Arguments:
        game_state: the GameState object.
        round_state: the RoundState object.
        active: your player's index.

        Returns:
        Nothing.
        '''
        print(f'Round {game_state.round_num}')
        my_bankroll = game_state.bankroll  # the total number of chips you've gained or lost from the beginning of the game to the start of this round
        game_clock = game_state.game_clock  # the total number of seconds your bot has left to play this game
        round_num = game_state.round_num  # the round number from 1 to NUM_ROUNDS
        my_cards = round_state.hands[active]  # your cards
        big_blind = bool(active)  # True if you are the big blind
        
        card1 = my_cards[0]
        card2 = my_cards[1]

        rank1 = card1[0] # "Ad", "9c", "Th" -> "A", "9", "T"
        suit1 = card1[1] # "d", "c", "h", etc.
        rank2 = card2[0]
        suit2 = card2[1]

        game_clock = game_state.game_clock
        num_rounds = game_state.round_num

        self.strong_hole = False
        if rank1 == rank2 or (rank1 in "AKQJT9876" and rank2 in "AKQJT9876"):
            self.strong_hole = True
        
        strength_w_auction, strength_wo_auction = self.calculate_strength(round_state, active, self.MONTE_CARLO_ITERS)
        self.strength_w_auction = strength_w_auction
        self.strength_wo_auction = strength_wo_auction
        print(f'\tHand: {" ".join(my_cards)}')

    def handle_round_over(self, game_state, terminal_state, active):
        '''
        Called when a round ends. Called NUM_ROUNDS times.

        Arguments:
        game_state: the GameState object.
        terminal_state: the TerminalState object.
        active: your player's index.

        Returns:
        Nothing.
        '''
        print()
        my_delta = terminal_state.deltas[active]  # your bankroll change from this round
        previous_state = terminal_state.previous_state  # RoundState before payoffs
        street = previous_state.street  # 0, 3, 4, or 5 representing when this round ended
        my_cards = previous_state.hands[active]  # your cards
        opp_cards = previous_state.hands[1-active]  # opponent's cards or [] if not revealed
        pass
    
    def get_action(self, game_state, round_state, active):
        '''
        Where the magic happens - your code should implement this function.
        Called any time the engine needs an action from your bot.

        Arguments:
        game_state: the GameState object.
        round_state: the RoundState object.
        active: your player's index.

        Returns:
        Your action.
        '''
        legal_actions = round_state.legal_actions()  # the actions you are allowed to take
        street = round_state.street  # 0, 3, 4, or 5 representing pre-flop, flop, turn, or river respectively
        my_cards = round_state.hands[active]  # your cards
        board_cards = round_state.deck[:street]  # the board cards
        my_pip = round_state.pips[active]  # the number of chips you have contributed to the pot this round of betting
        opp_pip = round_state.pips[1-active]  # the number of chips your opponent has contributed to the pot this round of betting
        my_stack = round_state.stacks[active]  # the number of chips you have remaining
        opp_stack = round_state.stacks[1-active]  # the number of chips your opponent has remaining
        my_bid = round_state.bids[active]  # How much you bid previously (available only after auction)
        opp_bid = round_state.bids[1-active]  # How much opponent bid previously (available only after auction)
        continue_cost = opp_pip - my_pip  # the number of chips needed to stay in the pot
        my_contribution = STARTING_STACK - my_stack  # the number of chips you have contributed to the pot
        opp_contribution = STARTING_STACK - opp_stack  # the number of chips your opponent has contributed to the pot
        pot = my_contribution + opp_contribution
        strength_diff = self.strength_w_auction - self.strength_wo_auction

        # Bidding logic
        if BidAction in legal_actions:
            max_bid = 200 if strength_diff > 0.2 else 100
            bid = int(max_bid * self.strength_w_auction) if not self.enough_chips_to_win_game(game_state, active) and \
                self.strength_w_auction > self.PROB_THRESHOLD \
                else 0
            return BidAction(bid)
        
        # Check/Fold if won enough chips to win game
        if self.enough_chips_to_win_game(game_state, active):
            return self.check_fold(legal_actions)

        print(f'\tBoard: {" ".join(board_cards)}')
        
        if RaiseAction in legal_actions:
            min_raise, max_raise = round_state.raise_bounds()
        
        strength = (self.strength_w_auction + self.strength_wo_auction)/2 if street < 3 else self.calculate_strength(round_state, active, self.MONTE_CARLO_ITERS)
        raise_cost = min(int(continue_cost + strength*max(pot, 20)), my_stack)
        print(f'\t\t{street}: {strength}')

        if RaiseAction in legal_actions:
            raise_ammt = my_pip + raise_cost
            raise_ammt = min(max(raise_ammt, min_raise), max_raise)
            commit_action = RaiseAction(raise_ammt)
        elif CallAction in legal_actions and continue_cost <= my_stack:
            commit_action = CallAction()
        else:
            commit_action = self.check_fold(legal_actions)

        if continue_cost > 0:
            pot_odds = continue_cost/(continue_cost + pot)

            if strength >= pot_odds:
                if strength > self.PROB_THRESHOLD and random.random() < strength + 0.2:
                    my_action = commit_action
                else:
                    my_action = CallAction()
            else:
                if self.rounds_fold_to_raise/game_state.round_num >= 0.3 and strength > self.PROB_THRESHOLD and random.random() < strength:
                    my_action = commit_action
                else:
                    my_action = FoldAction()
                    self.rounds_fold_to_raise += 1
        else:
            if strength > self.PROB_THRESHOLD and random.random() < strength + 0.2:
                my_action = commit_action
            else:
                my_action = CheckAction()
        
        return my_action

    """
    HELPER FUNCTIONS
    """

    def calculate_strength(self, round_state, active, iters):
        '''
        Calcualte win probabilities with and without winning auction if before auction, 
        or win probability after auction.

        Arguments:
        round_state: the RoundState object.
        active: your player's index.
        iters: number of iterations the simulation is ran.

        Returns:
        Win probability/probabilities.
        '''
        legal_actions = round_state.legal_actions()  # the actions you are allowed to take
        street = round_state.street  # 0, 3, 4, or 5 representing pre-flop, flop, turn, or river respectively
        my_cards = round_state.hands[active]  # your cards
        board_cards = round_state.deck[:street]  # the board cards
        after_auction = not (street == 0 or street == 3 and BidAction in legal_actions)

        deck = eval7.Deck()
        my_cards = [eval7.Card(card) for card in my_cards]
        for card in my_cards:
            deck.cards.remove(card)
        
        if after_auction:
            my_bid = round_state.bids[active]  # How much you bid previously (available only after auction)
            opp_bid = round_state.bids[1-active]  # How much opponent bid previously (available only after auction)
            won_bid = my_bid > opp_bid
            board_cards = [eval7.Card(card) for card in board_cards]
            for card in board_cards:
                deck.cards.remove(card)
            
            wins = 0
            for _ in range(iters):
                deck.shuffle()
                opp = 2 if won_bid else 3
                community_left = 5 - street
                draw = deck.peek(opp+community_left)
                opp_cards = draw[:opp]
                community_cards = draw[opp:] + board_cards

                our_hand = my_cards + community_cards
                opp_hand = opp_cards + community_cards

                our_hand_val = eval7.evaluate(our_hand)
                opp_hand_val = eval7.evaluate(opp_hand)

                if our_hand_val > opp_hand_val:
                    wins += 2
                elif our_hand_val == opp_hand_val:
                    wins += 1
                
            return wins / (2*iters)
        
        wins_wo_auction = 0
        for _ in range(iters):
            deck.shuffle()
            opp = 3
            community = 5
            draw = deck.peek(opp+community)
            opp_cards = draw[:opp]
            community_cards = draw[opp:]

            our_hand = my_cards + community_cards
            opp_hand = opp_cards + community_cards

            our_hand_val = eval7.evaluate(our_hand)
            opp_hand_val = eval7.evaluate(opp_hand)

            if our_hand_val > opp_hand_val:
                wins_wo_auction += 2
            elif our_hand_val == opp_hand_val:
                wins_wo_auction += 1

        wins_w_auction = 0
        for _ in range(iters):
            deck.shuffle()
            opp = 2
            community = 5
            auction = 1
            draw = deck.peek(opp+community+auction)
            opp_cards = draw[:opp]
            community_cards = draw[opp: opp + community]
            auction_card = draw[opp+community:]
            our_hand = my_cards + auction_card + community_cards
            opp_hand = opp_cards + community_cards

            our_hand_val = eval7.evaluate(our_hand)
            opp_hand_val = eval7.evaluate(opp_hand)

            if our_hand_val > opp_hand_val:
                wins_w_auction += 2
            elif our_hand_val == opp_hand_val:
                wins_w_auction += 1
            
            strength_w_auction = wins_w_auction / (2*iters)
            strength_wo_auction = wins_wo_auction/ (2*iters)

        return strength_w_auction, strength_wo_auction

    def enough_chips_to_win_game(self, game_state, active):
        '''
        Calculates if we have enough chips to check/fold the rest of the game.

        Arguments:
        game_state: the GameState object.
        active: your player's index.

        Returns:
        True if we have enough chips to check/fold the rest of the game, False otherwise.
        '''
        curr_big_blind = bool(active)
        remaining_rounds = NUM_ROUNDS - game_state.round_num + 1
        num_small_blinds = math.floor(remaining_rounds / 2) if curr_big_blind else math.ceil(remaining_rounds / 2)
        num_big_blinds = math.ceil(remaining_rounds / 2) if curr_big_blind else math.floor(remaining_rounds / 2)
        return game_state.bankroll - (SMALL_BLIND * num_small_blinds + BIG_BLIND * num_big_blinds) > 0
    
    def check_fold(self, legal_actions):
        '''
        Check if possible, else fold.

        Arguments:
        legal_actions: the legal actions.

        Returns:
        CheckAction if possible, else FoldAction.
        '''
        return CheckAction() if CheckAction in legal_actions else FoldAction()
        

if __name__ == '__main__':
    run_bot(Player(), parse_args())
