// LunaGo public site copy, English and French. Plain words, written for the customer.

import type { Lang } from "./api";

export const LANGS: Lang[] = ["en", "fr"];

export function isLang(value: string): value is Lang {
  return (LANGS as string[]).includes(value);
}

const en = {
  nav: { home: "LunaGo", help: "Help Center", contact: "Contact support", switch: "Français" },
  home: {
    title: "Rides and late-night food across Montréal.",
    lead: "One app to get home after the last metro, or to get poutine delivered at midnight.",
    helpTitle: "Something went wrong with a ride or an order?",
    helpLead:
      "Tell us what happened. Every message gets a ticket number, and you can watch it move from received to answered.",
    cta: "Contact support",
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
    lead: "Write in English or French. We reply by email, and you can follow your ticket here.",
    name: "Your name",
    namePlaceholder: "Optional",
    email: "Email",
    emailHint: "We send the reply and your ticket number here.",
    subject: "Subject",
    subjectPlaceholder: "Optional, e.g. Charged twice",
    message: "What happened?",
    messagePlaceholder: "Include the date of the ride or order if you can.",
    send: "Send message",
    sending: "Sending…",
    errorEmpty: "Write a message and an email address so we can reply.",
    errorNetwork: "The message could not be sent. Check your connection and try again.",
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
    emailNote: "A copy of every reply is sent to your email.",
  },
  footer:
    "LunaGo is a fictional company created for a university NLP project (ComplaintLens). Messages are processed by an AI system under human supervision.",
};

type Dict = typeof en;

const fr: Dict = {
  nav: { home: "LunaGo", help: "Centre d'aide", contact: "Contacter le support", switch: "English" },
  home: {
    title: "Courses et repas de fin de soirée partout à Montréal.",
    lead: "Une seule appli pour rentrer après le dernier métro, ou se faire livrer une poutine à minuit.",
    helpTitle: "Un problème avec une course ou une commande ?",
    helpLead:
      "Dites-nous ce qui s'est passé. Chaque message reçoit un numéro de ticket, et vous pouvez le suivre jusqu'à la réponse.",
    cta: "Contacter le support",
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
    lead: "Écrivez en français ou en anglais. Nous répondons par courriel et vous pouvez suivre votre ticket ici.",
    name: "Votre nom",
    namePlaceholder: "Facultatif",
    email: "Courriel",
    emailHint: "Nous y envoyons la réponse et votre numéro de ticket.",
    subject: "Objet",
    subjectPlaceholder: "Facultatif, p. ex. Facturé deux fois",
    message: "Que s'est-il passé ?",
    messagePlaceholder: "Indiquez la date de la course ou de la commande si possible.",
    send: "Envoyer le message",
    sending: "Envoi…",
    errorEmpty: "Écrivez un message et une adresse courriel pour que nous puissions répondre.",
    errorNetwork: "Le message n'a pas pu être envoyé. Vérifiez votre connexion et réessayez.",
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
    emailNote: "Une copie de chaque réponse est envoyée à votre courriel.",
  },
  footer:
    "LunaGo est une entreprise fictive créée pour un projet universitaire de TALN (ComplaintLens). Les messages sont traités par un système d'IA sous supervision humaine.",
};

export function dict(lang: Lang): Dict {
  return lang === "fr" ? fr : en;
}
export type { Dict };
