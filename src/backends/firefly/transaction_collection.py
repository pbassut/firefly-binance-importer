class TransactionCollection(object):
    def __init__(self, trade_data, _from_ff_account, _to_ff_account, _commission_ff_account, _from_commission_account):
        self.trade_data = trade_data
        self.from_ff_account = _from_ff_account
        self.to_ff_account = _to_ff_account
        self.commission_account = _commission_ff_account
        self.from_commission_account = _from_commission_account 
