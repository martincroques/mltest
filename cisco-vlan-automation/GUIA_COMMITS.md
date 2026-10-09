# Guia de commits sugeridos (apague este arquivo antes do commit final, se preferir)

Faça commits separados, um por etapa, para demonstrar uso real de Git. Sugestão de ordem:

```bash
git init -b main
git add .gitignore requirements.txt
git commit -m "chore: estrutura inicial, .gitignore e dependências"

git add README.md
git commit -m "docs: README inicial com descrição do projeto"

git add switch_automation.py
git commit -m "feat: backend com geração de comandos de VLAN, parsing e validação"

git add tests/
git commit -m "test: testes unitários de parsing e validação de configuração"

git add app.py templates/
git commit -m "feat: frontend Flask para configurar VLANs e hostname"

# (depois de testar no switch)
git add backups/ docs/
git commit -m "docs: evidências (prints) e backups de configuração"

git add README.md
git commit -m "docs: instruções de execução, notas e evidências no README"

git remote add origin https://github.com/<usuario>/<repo>.git
git push -u origin main
```

Dica: se achar um bug nos testes reais com o switch, corrija e faça um commit `fix: ...`. Isso fortalece o histórico.
