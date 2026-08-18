class DiseaseService:
    def __init__(self, repository):
        self.repository = repository

    def top(self, filters, limit):
        return self.repository.diseases_top(filters, limit)

