function financeApp() {
    return {
        mes: new Date().toISOString().slice(0, 7),
        hoje: new Date().toISOString().split('T')[0],
        categorias: [],
        despesas: [],
        dash: { total_gastos: 0, renda_mensal: 0, percentual_uso: 0, fechado: false, fixo: 0, variavel: 0, distribuicao_categoria: [] },
        form: { categoria_id: '', valor: '', vencimento: '', uso: 'FIXO' },
        senha: localStorage.getItem('finance_pass') || 'admin',
        modalAdmin: false,
        novaRenda: 0,
        chart: null,

        async init() {
            this.$watch('senha', (val) => localStorage.setItem('finance_pass', val));
            await this.carregarCategorias();
            await this.atualizarTudo();
        },

        get authHeader() { return { 'x-admin-password': this.senha }; },

        // Getters para as melhorias solicitadas
        get saldo_mes() {
            return this.dash.renda_mensal - this.dash.total_gastos;
        },
        get perc_fixo() {
            if (!this.dash.total_gastos) return 0;
            return Math.round((this.dash.fixo / this.dash.total_gastos) * 100);
        },
        get perc_variavel() {
            if (!this.dash.total_gastos) return 0;
            return Math.round((this.dash.variavel / this.dash.total_gastos) * 100);
        },

        async atualizarTudo() {
            try {
                const [resD, resK] = await Promise.all([
                    fetch(`http://127.0.0.1:8000/despesas-v2?mes=${this.mes}`),
                    fetch(`http://127.0.0.1:8000/dashboard-v2?mes=${this.mes}`)
                ]);
                this.despesas = await resD.json();
                this.dash = await resK.json();
                this.novaRenda = this.dash.renda_mensal;
                this.renderChart();
            } catch (e) { console.error("Sync Error"); }
        },

        isVencido(data) {
            return data < this.hoje;
        },

        async fecharMesAction() {
            if(!confirm("Encerrar este ciclo?")) return;
            const res = await fetch(`http://127.0.0.1:8000/config/fechar-mes?mes=${this.mes}`, { method: 'POST', headers: this.authHeader });
            if(res.ok) await this.atualizarTudo();
        },

        async reabrirMesAction() {
            const res = await fetch(`http://127.0.0.1:8000/config/reabrir-mes?mes=${this.mes}`, { method: 'POST', headers: this.authHeader });
            if(res.ok) { this.modalAdmin = false; await this.atualizarTudo(); }
        },

        async salvarDespesa() {
            const res = await fetch('http://127.0.0.1:8000/despesas-v2', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...this.authHeader },
                body: JSON.stringify({...this.form, mes: this.mes})
            });
            if(res.ok) { this.form = { categoria_id: '', valor: '', vencimento: '', uso: 'FIXO' }; await this.atualizarTudo(); }
        },

        async pagarDespesa(id) {
            const res = await fetch(`http://127.0.0.1:8000/despesas-v2/${id}/pagar`, { method: 'PATCH', headers: this.authHeader });
            if(res.ok) {
                // Correção de reatividade: atualização local imediata
                const idx = this.despesas.findIndex(d => d.id === id);
                if(idx !== -1) this.despesas[idx].pago = 1;
                
                // Refresh silencioso do dashboard para atualizar o gráfico/cards
                const resK = await fetch(`http://127.0.0.1:8000/dashboard-v2?mes=${this.mes}`);
                this.dash = await resK.json();
                this.renderChart();
            }
        },

        async excluirDespesa(id) {
            if(!confirm("Excluir?")) return;
            const res = await fetch(`http://127.0.0.1:8000/despesas-v2/${id}`, { method: 'DELETE', headers: this.authHeader });
            if(res.ok) await this.atualizarTudo();
        },

        async carregarCategorias() {
            const res = await fetch('http://127.0.0.1:8000/categorias');
            if(res.ok) this.categorias = await res.json();
        },

        formatarMoeda(v) { return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' }).format(v || 0); },

        renderChart() {
            const ctx = document.getElementById('chartCategorias');
            if(!ctx) return;
            if(this.chart) this.chart.destroy();
            this.chart = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Fixo', 'Variável'],
                    datasets: [{
                        data: [this.dash.fixo, this.dash.variavel],
                        backgroundColor: ['#6366f1', '#94a3b8'],
                        borderWidth: 0
                    }]
                },
                options: { cutout: '85%', plugins: { legend: { display: false } } }
            });
        }
    }
}