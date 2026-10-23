class Accounts {
    async request(url, options = {}) {
        return fetch(url, options);
    }
    async getAccount(id) {
        if (id) {
            return this.request(`${this.base}/accounts/${id}`);
        }
    }
    async removeAccount(id) {
        return this.request(`${this.base}/accounts/${id}`, { method: 'DELETE' });
    }
    async closeAccount(id) {
        throw new Error('Not supported');
    }
}
