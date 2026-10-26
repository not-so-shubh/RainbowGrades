#ifndef CONTACT_INFO_H
#define CONTACT_INFO_H

#include <string>

enum ContactField { CONTACT_LINKEDIN, CONTACT_GITHUB, CONTACT_WEBPAGE };

// Untrusted historical strings remain visible as escaped text when not valid links.
std::string ContactInfoHTML(const std::string &value, ContactField field);

#endif
