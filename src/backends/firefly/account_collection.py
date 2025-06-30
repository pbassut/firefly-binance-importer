class AccountCollection(object):
    def __init__(self, security, asset_account, expense_account, revenue_account):
        self.security = security
        self.asset_account = asset_account
        self.expense_account = expense_account
        self.revenue_account = revenue_account

    def __str__(self):
        return f"AccountCollection(security={self.security}, asset_account={self.asset_account}, expense_account={self.expense_account}, revenue_account={self.revenue_account})"
