import { connection } from "next/server";

export default async function Privacy() {
  await connection();
  const hosted = process.env.AVOIRLY_MODE === "hosted";
  const contact = (process.env.AVOIRLY_PUBLIC_CONTACT || "").trim();
  const contactHref = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(contact)
    ? `mailto:${contact}`
    : /^https:\/\/[^\s]+$/.test(contact)
      ? contact
      : null;
  return (
    <article className="privacy-content">
      <div className="eyebrow">VOS DOCUMENTS · PILOTE PRIVÉ</div>
      <h1>Un traitement que vous contrôlez.</h1>
      <section className="panel panel-body">
        <h2>Un pilote avec des données synthétiques</h2>
        <p>
          Ce déploiement est réservé aux deux comptes de test autorisés. Les
          inscriptions publiques sont désactivées. N’importez pas de documents
          réels de fournisseur avant l’ouverture explicite du pilote à ses
          participants et la confirmation des informations de contact.
        </p>
        <h2>Ce que fait Avoirly</h2>
        <p>
          Avoirly conserve vos bons de commande, factures, données extraites,
          corrections et brouillons pour comparer les documents et documenter
          les écarts. Le suivi manuel conserve les déclarations d’envoi, notes,
          promesses, avoirs reçus et justificatifs. Avoirly n’envoie aucun
          e-mail au fournisseur. Des alertes techniques sans documents ni
          extraits de journaux sont envoyées à l’opérateur par Gmail SMTP.
        </p>
        <h2>Accès et lieux de traitement</h2>
        <p>
          Chaque propriétaire accède à ses dossiers via l’application.
          L’opérateur dispose d’un accès administratif pour assurer le service.
          {hosted
            ? " L’application, Supabase Auth, PostgreSQL et le stockage privé sont auto-hébergés sur Oracle Cloud à Casablanca, au Maroc. Render et les projets Supabase gérés ne sont pas utilisés par ce déploiement."
            : " En mode local, les dossiers et fichiers sont conservés sur l’ordinateur de développement ; ce mode ne doit pas être exposé sur Internet."}
        </p>
        <p>
          Les copies de secours chiffrées sont conservées sur le serveur puis
          copiées sur le poste Windows de l’opérateur, hors du dossier OneDrive.
          Cette copie dépend de la disponibilité de ce poste et de sa connexion.
          Les services externes décrits ci-dessous peuvent traiter des données
          hors du Maroc ; aucune résidence exclusivement marocaine n’est
          promise.
        </p>
        <h2>Extraction automatique et prestataires</h2>
        <p>
          Une extraction automatique transmet le contenu du bon de commande et
          de la facture à OpenAI. La saisie complète et la vérification
          manuelles permettent une comparaison sans appel au modèle. Les
          justificatifs d’avoirs ne sont pas envoyés au modèle pour extraction.
        </p>
        <p>
          La conservation des réponses via l’API est désactivée. Cela ne
          constitue pas une garantie de conservation nulle chez OpenAI. Les
          contrôles et la région du projet fournisseur n’ont pas été attestés
          pour des documents réels. Consultez la{" "}
          <a href="https://developers.openai.com/api/docs/guides/your-data">
            politique OpenAI relative aux données API
          </a>
          . Gmail reçoit l’adresse de l’opérateur et le contenu minimal des
          alertes techniques, pas les documents des dossiers.
        </p>
        <h2>Conservation et suppression</h2>
        <p>
          Les dossiers restent conservés jusqu’à leur suppression manuelle. Il
          n’existe pas de suppression automatique à 30 jours. « Supprimer le
          dossier » révoque immédiatement l’accès et retire les données actives
          ; si le stockage est indisponible, le retrait physique des fichiers
          est relancé par le worker.
        </p>
        <p>
          Les sauvegardes chiffrées sont conservées pendant 14 jours. Leur purge
          dépend du succès des tâches correspondantes. Une restauration doit
          tenir compte des suppressions intervenues après la sauvegarde. Les
          compteurs de quotas et les estimations d’usage technique peuvent
          subsister après la suppression d’un dossier, jusqu’à une purge
          administrative. Les journaux des conteneurs sont limités en volume ;
          les prestataires et le système disposent de leurs propres règles.
        </p>
        <h2>Contact et limites du pilote</h2>
        <p>
          {contactHref ? (
            <>
              Pour les questions d’accès, de suppression ou de conservation :{" "}
              <a href={contactHref}>{contact}</a>.
            </>
          ) : (
            <>
              Le contact public de confidentialité et d’assistance sera ajouté
              avant l’accueil de participants réels. Pour ce pilote synthétique,
              contactez directement l’opérateur qui vous a fourni l’accès.
            </>
          )}
        </p>
        <p>
          Un écart potentiel n’est ni un avoir confirmé ni une somme récupérée.
          Vérifiez les sources et le brouillon. N’importez que les documents que
          vous êtes autorisé à traiter.
        </p>
        <p>Informations mises à jour le 16 octobre 2026.</p>
      </section>
    </article>
  );
}
