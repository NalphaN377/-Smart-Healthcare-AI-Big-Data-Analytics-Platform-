class CostService:
    def __init__(self, repository):
        self.repository = repository

    def diseases(self, filters, limit):
        return self.repository.diseases_cost(filters, limit)

    def hospitals(self, filters, limit):
        return self.repository.hospitals_cost(filters, limit)

