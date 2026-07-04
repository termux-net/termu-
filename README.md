# Omega AI Chat

Plateforme de chat IA avec Gemini 2.5 Flash, système VIP et paiement Mobile Money.

## Déploiement sur Render

1. Créez un compte sur [Render](https://render.com)
2. Connectez votre repo GitHub
3. Render détectera automatiquement le `render.yaml`
4. Ajoutez vos clés API Gemini via le panel admin après déploiement

## Fonctionnalités

- ✅ Inscription par téléphone avec validation manuelle
- ✅ Détection d'IP anti-multi-comptes
- ✅ 3 niveaux VIP (1000/2500/5000 FCFA/semaine)
- ✅ Discussions éphémères (gratuit) ou persistantes (VIP 2+)
- ✅ Mode réflexion (thinking budget)
- ✅ Upload de fichiers et images
- ✅ Rotation de clés API (5 req/min par clé)
- ✅ Panel admin complet
- ✅ Paiement manuel via WhatsApp

## Configuration Admin

Après déploiement :
1. Créez un utilisateur manuellement en BDD avec `is_admin=True`
2. Connectez-vous et allez sur `admin.html`
3. Ajoutez vos clés API Gemini
4. Configurez le prompt système
5. Validez les utilisateurs et paiements

## Support

WhatsApp: +225 XX XX XX XX
