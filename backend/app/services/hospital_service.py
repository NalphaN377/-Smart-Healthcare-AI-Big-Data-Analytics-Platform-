class HospitalService:
    def __init__(self, repository):
        self.repository = repository

    def top(self, filters, limit):
        return self.repository.hospitals_top(filters, limit)

