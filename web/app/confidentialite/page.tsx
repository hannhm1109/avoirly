export default function Privacy() {
  return (
    <article className="privacy-content">
      <div className="eyebrow">VOS DOCUMENTS</div>
      <h1>Un traitement que vous contrôlez.</h1>
      <section className="panel panel-body">
        <h2>Ce que fait Avoirly</h2>
        <p>
          Avoirly conserve vos bons de commande, factures, données extraites,
          corrections et brouillons afin de comparer vos documents et de
          documenter les écarts. Le suivi manuel conserve aussi vos déclarations
          d’envoi, notes fournisseur, montants promis, avoirs reçus et leurs
          justificatifs. Aucun e-mail n’est envoyé automatiquement.
        </p>
        <h2>Extraction automatique</h2>
        <p>
          Quand vous lancez une extraction automatique, le contenu des documents
          est transmis à OpenAI. Vous pouvez aussi saisir et vérifier les
          valeurs manuellement. Les justificatifs d’avoirs du suivi manuel ne
          sont pas envoyés au modèle pour extraction. N’importez que les
          documents que vous êtes autorisé à traiter.
        </p>
        <h2>Accès et conservation</h2>
        <p>
          Dans la version hébergée, seuls les comptes invités peuvent utiliser
          l’application. Les dossiers sont accessibles uniquement à leur
          propriétaire via l’application. L’opérateur dispose d’un accès
          administratif pour assurer le service. Supabase gère
          l’authentification, la base de données et le stockage privé ; Render
          exécute l’application.
        </p>
        <p>
          Les dossiers restent conservés jusqu’à leur suppression par leur
          propriétaire ou la fin du pilote. L’opérateur confirme les régions
          d’hébergement et les durées effectives des sauvegardes avant votre
          invitation.
        </p>
        <h2>Suppression</h2>
        <p>
          « Supprimer le dossier » révoque immédiatement l’accès et retire les
          données actives. Si le stockage est momentanément indisponible, la
          suppression du fichier est relancée. Des copies peuvent subsister dans
          les sauvegardes pendant leur durée de conservation ; l’opérateur doit
          les prendre en compte lors d’une restauration.
        </p>
        <h2>Questions et limites</h2>
        <p>
          Contactez la personne qui vous a invité pour une demande d’accès, de
          suppression ou une question sur la conservation. Un écart potentiel
          n’est ni un avoir confirmé ni une somme récupérée. Le pilote nécessite
          votre vérification des sources et du brouillon.
        </p>
      </section>
    </article>
  );
}
