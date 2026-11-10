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
      "Tell us what happened. Every message gets a ticket number, and you can watch it move from received to answered.",
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
  help: { title: "Help Center", lead: "Our policies, written plainly. Replies from support quote these pages." },
  contact: {
    title: "Contact support",
    lead: "Write in English or French. You get a ticket number right away, and our reply appears on your ticket's page.",
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
      chat: ["Live chat", "Ask on this website and read the answer in the conversation.", "Open the chat"],
      rate: ["Rate your last trip", "Stars and a comment. Low ratings are read by our team.", "Rate a trip"],
      email: ["Email", "Write to us; your email gets a ticket like any other message. In this demo our inbox receives only, so to read our answer use the form or the chat.", ""],
      forum: ["Community forum", "Ask in public. Our answer is posted in the thread.", "Open the forum"],
    },
  },
  chat: {
    open: "Chat with us",
    close: "Close the chat",
    title: "LunaGo support",
    intro: "Tell us what happened. We answer here within seconds, or tell you who is looking into it.",
    email: "Your email",
    emailHint: "Used to find your rides and orders.",
    placeholder: "Write your message",
    send: "Send",
    working: "Reading your message",
    track: "Follow this ticket",
    again: "Ask something else",
    error: "The message could not be sent. Try again in a moment.",
  },
  rate: {
    title: "Rate your last trip",
    lead: "How was it? We read every rating of 3 stars or less, and may reply.",
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
    title: "Your request",
    ticket: "Ticket",
    reply: "Reply from LunaGo",
    waiting: "We are reading your message.",
    review: "A member of our team is reviewing your message.",
    escalated: "Your report is with our Safety team.",
    noReply: "Thanks for your message. No reply is needed, but it has been recorded.",
    notFound: "This tracking link is not valid. Use the link from your confirmation email.",
    emailNote: "Keep this page's address: our replies appear here.",
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
      "Dites-nous ce qui s'est passé. Chaque message reçoit un numéro de ticket, et vous pouvez le suivre jusqu'à la réponse.",
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
    lead: "Nos politiques, expliquées simplement. Les réponses du support citent ces pages.",
  },
  contact: {
    title: "Contacter le support",
    lead: "Écrivez en français ou en anglais. Vous recevez tout de suite un numéro de ticket, et notre réponse s'affiche sur la page de votre ticket.",
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
      chat: ["Clavardage", "Posez votre question sur ce site et lisez la réponse dans la conversation.", "Ouvrir le clavardage"],
      rate: ["Évaluer votre dernière course", "Des étoiles et un commentaire. Notre équipe lit les mauvaises notes.", "Évaluer une course"],
      email: ["Courriel", "Écrivez-nous ; votre courriel reçoit un ticket comme tout autre message. Dans cette démo, notre boîte ne fait que recevoir : pour lire notre réponse, utilisez le formulaire ou le clavardage.", ""],
      forum: ["Forum communautaire", "Posez votre question en public. Notre réponse est publiée dans la discussion.", "Ouvrir le forum"],
    },
  },
  chat: {
    open: "Clavarder avec nous",
    close: "Fermer le clavardage",
    title: "Support LunaGo",
    intro: "Dites-nous ce qui s'est passé. Nous répondons ici en quelques secondes, ou nous vous disons qui s'en occupe.",
    email: "Votre courriel",
    emailHint: "Sert à retrouver vos courses et commandes.",
    placeholder: "Écrivez votre message",
    send: "Envoyer",
    working: "Nous lisons votre message",
    track: "Suivre ce ticket",
    again: "Poser une autre question",
    error: "Le message n'a pas pu être envoyé. Réessayez dans un instant.",
  },
  rate: {
    title: "Évaluer votre dernière course",
    lead: "Comment s'est-elle passée ? Nous lisons chaque note de 3 étoiles ou moins, et pouvons vous répondre.",
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
    title: "Votre demande",
    ticket: "Ticket",
    reply: "Réponse de LunaGo",
    waiting: "Nous lisons votre message.",
    review: "Un membre de notre équipe examine votre message.",
    escalated: "Votre signalement est entre les mains de notre équipe Sécurité.",
    noReply: "Merci pour votre message. Aucune réponse n'est nécessaire, mais il a bien été enregistré.",
    notFound: "Ce lien de suivi n'est pas valide. Utilisez le lien de votre courriel de confirmation.",
    emailNote: "Gardez l'adresse de cette page : nos réponses s'y affichent.",
  },
  footer:
    "LunaGo est une entreprise fictive créée pour un projet universitaire de TALN (ComplaintLens). Les messages sont traités par un système d'IA sous supervision humaine.",
};

export function dict(lang: Lang): Dict {
  return lang === "fr" ? fr : en;
}
export type { Dict };
