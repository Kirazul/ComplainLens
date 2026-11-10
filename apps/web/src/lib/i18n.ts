// LunaGo public site copy, English and French. Plain words, written for the customer.

import type { Lang } from "./api";

export const LANGS: Lang[] = ["en", "fr"];

export function isLang(value: string): value is Lang {
  return (LANGS as string[]).includes(value);
}

const en = {
  nav: {
    home: "LunaGo",
    help: "Help Center",
    rate: "Rate a trip",
    community: "Community",
    contact: "Contact support",
    switch: "Français",
  },
  home: {
    title: "Rides and late‑night food across Montréal.",
    lead: "One app to get home after the last metro, or to get poutine delivered at midnight.",
    helpTitle: "Something went wrong with a ride or an order?",
    helpLead:
      "Tell us what happened. Most answers arrive in seconds; otherwise someone from our team replies.",
    cta: "Chat with us",
    write: "Write to support",
    browse: "Browse the Help Center",
    topics: "Common questions",
    phasesTitle: "How your request moves",
  },
  phases: {
    received: "Received",
    understood: "Understood",
    routed: "With the right team",
    answered: "Answered",
  },
  help: { title: "Help Center", lead: "Our policies, written plainly." },
  contact: {
    title: "Contact support",
    lead: "Write in English or French. Our reply appears on your ticket page.",
    name: "Your name",
    namePlaceholder: "Optional",
    email: "Email",
    emailHint: "Used to find your rides and orders. We never share it.",
    subject: "Subject",
    subjectPlaceholder: "Optional, e.g. Charged twice",
    message: "What happened?",
    messagePlaceholder: "Include the date of the ride or order if you can.",
    send: "Send message",
    sending: "Sending…",
    errorEmpty: "Write a message and an email address so we can reply.",
    errorNetwork: "The message could not be sent. Check your connection and try again.",
    errorBusy: "Too many messages from this connection. Try again in an hour.",
    otherWays: "Other ways to reach us",
    channels: {
      chat: ["Live chat", "Answers in seconds, right here.", "Open the chat"],
      rate: ["Rate your last trip", "Stars and a comment.", "Rate a trip"],
      email: ["Email", "This demo inbox only receives. For an answer, use the chat or the form.", ""],
      forum: ["Community forum", "Ask in public; we answer in the thread.", "Open the forum"],
    },
  },
  chat: {
    open: "Chat with us",
    close: "Close the chat",
    title: "LunaGo support",
    intro: "Hi! Tell us what happened and we will sort it out.",
    email: "Your email",
    emailHint: "Enter a valid email address.",
    placeholder: "What happened?",
    newChat: "New chat",
    fullPage: "Open as a page",
  },
  conversation: {
    assistant: "LunaGo assistant",
    team: "LunaGo",
    writing: "LunaGo is writing…",
    placeholder: "Write a message",
    send: "Send",
    busy: "Too many messages from this connection. Try again in an hour.",
    error: "The message could not be sent. Try again.",
  },
  rate: {
    title: "Rate your last trip",
    lead: "How was it?",
    stars: "Your rating",
    star: ["1 star, very bad", "2 stars, bad", "3 stars, okay", "4 stars, good", "5 stars, excellent"],
    comment: "What happened?",
    commentPlaceholder: "Optional for 4 or 5 stars",
    commentNeeded: "Tell us what went wrong so we can fix it.",
    pickStars: "Choose a rating from 1 to 5 stars.",
    subject: "Trip rating: {n}/5",
    send: "Send rating",
  },
  track: {
    title: "Your conversation",
    ticket: "Ticket",
    waiting: "We are reading your message.",
    review: "Our team is on it.",
    escalated: "Our Safety team is on it.",
    noReply: "Thanks, your message is recorded.",
    closed: "Resolved. Write again if you need anything.",
    notFound: "This link is not valid.",
    keep: "Bookmark this page to come back to the conversation.",
  },
  footer:
    "LunaGo is a fictional company created for a university NLP project (ComplaintLens). Messages are processed by an AI system under human supervision.",
};

type Dict = typeof en;

const fr: Dict = {
  nav: {
    home: "LunaGo",
    help: "Centre d'aide",
    rate: "Évaluer une course",
    community: "Communauté",
    contact: "Contacter le support",
    switch: "English",
  },
  home: {
    title: "Courses et repas de fin de soirée partout à Montréal.",
    lead: "Une seule appli pour rentrer après le dernier métro, ou se faire livrer une poutine à minuit.",
    helpTitle: "Un problème avec une course ou une commande ?",
    helpLead:
      "Dites-nous ce qui s'est passé. La plupart des réponses arrivent en quelques secondes ; sinon, notre équipe vous répond.",
    cta: "Clavarder avec nous",
    write: "Écrire au support",
    browse: "Consulter le centre d'aide",
    topics: "Questions fréquentes",
    phasesTitle: "Le parcours de votre demande",
  },
  phases: {
    received: "Reçue",
    understood: "Comprise",
    routed: "Transmise à la bonne équipe",
    answered: "Répondue",
  },
  help: {
    title: "Centre d'aide",
    lead: "Nos politiques, expliquées simplement.",
  },
  contact: {
    title: "Contacter le support",
    lead: "Écrivez en français ou en anglais. Notre réponse s'affiche sur la page de votre ticket.",
    name: "Votre nom",
    namePlaceholder: "Facultatif",
    email: "Courriel",
    emailHint: "Sert à retrouver vos courses et commandes. Nous ne le partageons jamais.",
    subject: "Objet",
    subjectPlaceholder: "Facultatif, p. ex. Facturé deux fois",
    message: "Que s'est-il passé ?",
    messagePlaceholder: "Indiquez la date de la course ou de la commande si possible.",
    send: "Envoyer le message",
    sending: "Envoi…",
    errorEmpty: "Écrivez un message et une adresse courriel pour que nous puissions répondre.",
    errorNetwork: "Le message n'a pas pu être envoyé. Vérifiez votre connexion et réessayez.",
    errorBusy: "Trop de messages depuis cette connexion. Réessayez dans une heure.",
    otherWays: "Autres façons de nous joindre",
    channels: {
      chat: ["Clavardage", "Des réponses en quelques secondes, ici même.", "Ouvrir le clavardage"],
      rate: ["Évaluer votre dernière course", "Des étoiles et un commentaire.", "Évaluer une course"],
      email: ["Courriel", "Cette boîte de démo ne fait que recevoir. Pour une réponse, utilisez le clavardage ou le formulaire.", ""],
      forum: ["Forum communautaire", "Posez votre question en public ; nous répondons dans la discussion.", "Ouvrir le forum"],
    },
  },
  chat: {
    open: "Clavarder avec nous",
    close: "Fermer le clavardage",
    title: "Support LunaGo",
    intro: "Bonjour ! Dites-nous ce qui s'est passé, on s'en occupe.",
    email: "Votre courriel",
    emailHint: "Entrez une adresse courriel valide.",
    placeholder: "Que s'est-il passé ?",
    newChat: "Nouvelle discussion",
    fullPage: "Ouvrir en pleine page",
  },
  conversation: {
    assistant: "Assistant LunaGo",
    team: "LunaGo",
    writing: "LunaGo écrit…",
    placeholder: "Écrivez un message",
    send: "Envoyer",
    busy: "Trop de messages depuis cette connexion. Réessayez dans une heure.",
    error: "Le message n'a pas pu être envoyé. Réessayez.",
  },
  rate: {
    title: "Évaluer votre dernière course",
    lead: "Comment s'est-elle passée ?",
    stars: "Votre note",
    star: ["1 étoile, très mauvais", "2 étoiles, mauvais", "3 étoiles, correct", "4 étoiles, bien", "5 étoiles, excellent"],
    comment: "Que s'est-il passé ?",
    commentPlaceholder: "Facultatif pour 4 ou 5 étoiles",
    commentNeeded: "Dites-nous ce qui n'a pas fonctionné pour que nous puissions corriger.",
    pickStars: "Choisissez une note de 1 à 5 étoiles.",
    subject: "Évaluation de la course : {n}/5",
    send: "Envoyer la note",
  },
  track: {
    title: "Votre conversation",
    ticket: "Ticket",
    waiting: "Nous lisons votre message.",
    review: "Notre équipe s'en occupe.",
    escalated: "Notre équipe Sécurité s'en occupe.",
    noReply: "Merci, votre message est enregistré.",
    closed: "Réglé. Écrivez-nous si besoin.",
    notFound: "Ce lien n'est pas valide.",
    keep: "Ajoutez cette page à vos favoris pour revenir à la conversation.",
  },
  footer:
    "LunaGo est une entreprise fictive créée pour un projet universitaire de TALN (ComplaintLens). Les messages sont traités par un système d'IA sous supervision humaine.",
};

export function dict(lang: Lang): Dict {
  return lang === "fr" ? fr : en;
}
export type { Dict };
