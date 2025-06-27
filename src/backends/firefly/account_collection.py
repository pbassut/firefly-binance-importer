class AccountCollection(object):
    def __init__(self, security):
        self.security = security
        self.asset_account = None
        self.expense_account = None
        self.revenue_account = None

    def set_expense_account(self, _expense_account):
        self.expense_account = _expense_account

    def set_revenue_account(self, _revenue_account):
        self.revenue_account = _revenue_account

    def set_asset_account(self, _asset_account):
        self.asset_account = _asset_account 
