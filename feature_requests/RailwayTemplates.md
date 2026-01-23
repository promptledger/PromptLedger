# Create a Template
---
title: Create a Template
description: Learn how to create reusable templates on Railway to enable effortless one-click deploys.
---

Creating a template allows you to capture your infrastructure in a reusable and distributable format.

By defining services, environment configuration, network settings, etc., you lay the foundation for others to deploy the same software stack with the click of a button.

If you [publish your template](/guides/publish-and-share) to the <a href="https://railway.com/templates" target="_blank">marketplace</a>, you can earn kickbacks from usage, up to 50% for open source templates with active community support. Learn more about the [kickback program](/reference/templates#kickback-program).

## How to Create a Template

You can either create a template from scratch or base it off of an existing project.

### Starting from Scratch

To create a template from scratch, head over to your <a href="https://railway.com/workspace/templates" target="_blank">Templates</a> page within your workspace settings and click on the `New Template` button.

- Add a service by clicking the `Add New` button in the top right-hand corner, or through the command palette (`CMD + K` -> `+ New Service`)
- Select the service source (GitHub repo or Docker Image)
- Configure the service variables and settings

  <Image src="https://res.cloudinary.com/railway/image/upload/v1715724184/docs/templates-v2/composer_aix1x8.gif"
  alt="Template Editor"
  layout="intrinsic"
  width={900} height={1120} quality={80} />

- Once you've added your services, click `Create Template`
- You will be taken to your templates page where you can copy the template URL to share with others

Note that your template will not be available on the template marketplace, nor will be eligible for a kickback, until you [publish](/guides/publish-and-share) it.

### Private Repo Support

It's now possible to specify a private GitHub repo when creating a template.

This feature is intended for use among [Teams](/reference/teams) and [Organizations](/reference/teams). Users supporting a subscriber base may also find this feature helpful to distribute closed-source code.

To deploy a template that includes a private repo, look for the `GitHub` panel in the `Account Integrations` section of [General Settings](https://railway.com/account). Then select the `Edit Scope` option to grant Railway access to the desired private repos.

<Image
src="https://res.cloudinary.com/railway/image/upload/v1721350229/docs/github-private-repo_m46wxu.png"
alt="Create a template from a private GitHub repositories"
layout="intrinsic"
width={1599}
height={899}
quality={80}
/>

If you do not see the `Edit Scope` option, you may still need to connect GitHub to your Railway account.

### Convert a Project Into a Template

You can also convert an existing project into a ready-made Template for other users.

- From your project page, click `Settings` in the right-hand corner of the canvas
- Scroll down until you see **Generate Template from Project**
- Click `Create Template`

<Image
src="https://res.cloudinary.com/railway/image/upload/v1743198969/docs/create-template_ml13wy.png"
alt="Generate template from project"
layout="intrinsic"
width={1200}
height={380}
quality={80}
/>

- You will be taken to the template composer page, where you should confirm the settings and finalize the template creation

## Configuring Services

Configuring services using the template composer is very similar to building a live project in the canvas.

Once you add a new service and select the source, you can configure the following to enable successful deploys for template users:

- **Variables tab**
  - Add required [Variables](/guides/variables).
    _Use [reference variables](/guides/variables#reference-variables) where possible for a better quality template_
- **Settings tab**
  - Add a [Root Directory](/guides/monorepo) (Helpful for monorepos)
  - [Enable Public Networking](/guides/public-networking) with TCP Proxy or HTTP
  - Set a custom [Start command](/guides/start-command)
  - Add a [Healthcheck Path](/guides/healthchecks#configure-the-healthcheck-path)
- **Add a volume**
  - To add a volume to a service, right-click on the service, select Attach Volume, and specify the [Volume mount path](/guides/volumes)

### Specifying a Branch

To specify a particular GitHub branch to deploy, simply enter the full URL to the desired branch in the Source Repo configuration. For example -

- This will deploy the `main` branch: `https://github.com/railwayapp-templates/postgres-ssl`
- This will deploy the `new` branch: `https://github.com/railwayapp-templates/postgres-ssl/tree/new`

### Template Variable Functions

Template variable functions allow you to dynamically generate variables (or parts of a variable) on demand when the template is deployed.

<Image src="https://res.cloudinary.com/railway/image/upload/v1743198983/docs/template-variables_dp5pg5.png"
alt="Template Variable Functions"
layout="intrinsic"
width={1200} height={428} quality={100} />

When a template is deployed, all template variable functions are executed and the result replaces the `${{ ... }}` in the variable.

Use template variables to generate a random password for a database, or to generate a random string for a secret.

The current template variable functions are:

1. `secret(length?: number, alphabet?: string)`: Generates a random secret (32 chars by default).

   **Tip:** You can generate Hex or Base64 secrets by constructing the appropriate alphabet and length.

   - `openssl rand -base64 16` → `${{secret(22, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/")}}==`
   - `openssl rand -base64 32` → `${{secret(43, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/")}}=`
   - `openssl rand -base64 64` → `${{secret(86, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789+/")}}==`
   - `openssl rand -hex 16` → `${{secret(32, "abcdef0123456789")}}`
   - `openssl rand -hex 32` → `${{secret(64, "abcdef0123456789")}}`
   - `openssl rand -hex 64` → `${{secret(128, "abcdef0123456789")}}`

   Or even generate a UUIDv4 string -

   `${{secret(8, "0123456789abcdef")}}-${{secret(4, "0123456789abcdef")}}-4${{secret(3, "0123456789abcdef")}}-${{secret(1, "89ab")}}${{secret(3, "0123456789abcdef")}}-${{secret(12, "0123456789abcdef")}}`

2. `randomInt(min?: number, max?: number)`: Generates a random integer between min and max (defaults to 0 and 100)

## Managing Your Templates

You can see all of your templates on your <a href="https://railway.com/workspace/templates" target="_blank">Workspace's Template page</a>. Templates are separated into Personal and Published templates.

You can edit, publish/unpublish and delete templates.

<Image src="https://res.cloudinary.com/railway/image/upload/v1743199089/docs/templates_xyphou.png"
 alt="Account templates page"
 layout="intrinsic"
 width={1200}
 height={668}
 quality={80}
/>

# Template Best Practices
---
title: Template Best Practices
description: Learn the best practices for template creation.
---

Creating templates can get complex, but these best practices will help you create templates that are easy to use and maintain.

## Checklist

Depending on the type of template, there are different things to consider:

- [Template and Service Icons](#template-and-service-icons)
- [Naming Conventions](#naming-conventions)
- [Private Networking](#private-networking)
- [Environment Variables](#environment-variables)
- [Health Checks](#health-checks)
- [Persistent Storage](#persistent-storage)
- [Authentication](#authentication)
- [Dry Code](#dry-code)
- [Workspace Naming](#workspace-naming)
- [Overview](#overview)

## Template and Service Icons

Template and service icons are important for branding and recognition, as they give the template a more professional look and feel.

Always use 1:1 aspect ratio icons or logos with transparent backgrounds for both the template itself and the services the template includes.

Transparent backgrounds ensure logos integrate seamlessly with Railway's interface and provide a more polished, professional appearance.

## Naming Conventions

Naming conventions are important for readability and consistency; using proper names enhances the overall quality and credibility of your template.

Always follow the naming conventions for the software that the template is made for.

Example, if the template is for ClickHouse, the service and template name should be named `ClickHouse` with a capital C and H, since that is how the brand name is spelled.

For anything else, such as custom software:

- Use capital case.
- Avoid using special characters or dashes, space-delimited is the way to go.
- Prefer shorter names over longer names for better readability.
- Keep names concise while maintaining clarity.

## Private Networking

Private networking provides faster, free communication between services and reduces costs compared to routing traffic through the public internet.

Always configure service-to-service communication (such as backend to database connections) to use private network hostnames rather than public domains.

For more details, see the [private networking guide](/guides/private-networking) and [reference documentation](/reference/private-networking).

## Environment Variables

Properly set up environment variables are a great way to increase the usability of your template.

When using environment variables:

- Always include a description of what the variable is for.

- If a variable is optional, include a description explaining its purpose and what to set it to or where to find its value.

- For any secrets, passwords, keys, etc., use [template variable functions](/guides/create#template-variable-functions) to generate them, avoid hardcoding default credentials at all costs.

- Use [reference variables](/guides/variables#referencing-another-services-variable) when possible for dynamic service configuration.

- When referencing a hostname, use the private network hostname rather than the public domain, e.g., `RAILWAY_PRIVATE_DOMAIN` rather than `RAILWAY_PUBLIC_DOMAIN`.

- Include helpful pre-built variables that the user may need, such as database connection strings, API keys, hostnames, ports, and so on.

## Health Checks

Health checks are important for ensuring that the service is running properly, before traffic is routed to it.

Although a health check might not be needed for all software, such as Discord bots, when it is applicable, it is a good idea to include a health check.

A readiness endpoint is the best option; if that's not possible, then a liveness endpoint should be used.

For more details, see the [healthchecks guide](/guides/healthchecks) and [reference documentation](/reference/healthchecks).

## Persistent Storage

Persistent storage is essential for templates that include databases, file servers, or other stateful services that need to retain data across deployments.

Always include a volume for these services.

Without persistent storage, data will be lost between redeployments, leading to unrecoverable data loss for template users.

When configuring the service, ensure the volume is mounted to the correct path. An incorrect mount path will prevent data from being stored in the volume.

Some examples of software that require persistent storage:

- **Databases:** PostgreSQL, MySQL, MongoDB, etc.
- **File servers:** Nextcloud, ownCloud, etc.
- **Other services:** Redis, RabbitMQ, etc.

The volume mount location depends entirely on where the software expects it to be mounted. Refer to the software's documentation for the correct mount path.

For more details, see the [volumes guide](/guides/volumes) and [reference documentation](/reference/volumes).

## Authentication

Authentication is a common feature for many software applications, and it is crucial to properly configure it to prevent unauthorized access.

If the software provides a way to configure authentication, such as a username and password, or an API key, you should always configure it in the template.

For example, ClickHouse can operate without authentication, but authentication should always be configured so as not to leave the database open and unauthenticated to the public.

Passwords, API keys, etc. should be generated using [template variable functions](/guides/create#template-variable-functions), and not hardcoded.

## Dry Code

This is most applicable to templates that deploy from GitHub.

When creating templates that deploy from GitHub, include only the essential files needed for deployment. Avoid unnecessary documentation, example files, or unused code and configurations that don't contribute to the core functionality.

A clean, minimal repository helps users quickly understand the template's structure and make customizations when needed.

## Workspace Naming

When users deploy a template, the template author appears as the name of the <a href="/reference/teams" target="_blank">workspace</a> that created and published it.

Since the author is publicly visible and shown with the template to the users, it is important to make sure the workspace name is professional and **accurately represents your relationship to the software**.

**Important:** Only use a company or organization name as your workspace name if you are officially authorized to represent that entity. Misrepresenting your affiliation is misleading to users and violates trust.

**If you are officially affiliated** with the software (e.g., you work for ClickHouse and are creating a ClickHouse template), then using the official company name "ClickHouse, Inc." is appropriate and helpful for users to identify official templates.

**If you are not officially affiliated** with the software, always use your own professional name as the workspace name.

**Note:** To transfer a template from one workspace to another, <a href="https://station.railway.com/" target="_blank">contact support</a>.

## Overview

The overview is the first thing users will see when they click on the template, so it is important to make it count.

The overview should include the following:

- **H1: Deploy and Host [X] with Railway**

  What is X? Your description in roughly ~ 50 words.

- **H2: About Hosting [X]**

  Roughly 100 word description what's involved in hosting/deploying X

- **H2: Common Use Cases**

  In 3-5 bullets, what are the most common use cases for [X]?

- **H2: Dependencies for [X] Hosting**

  In bullet form, what other technologies are incorporated in using this template besides [X]?

- **H3: Deployment Dependencies**

  Include any external links relevant to the template.

- **H3: Implementation Details (Optional)**

  Include any code snippets or implementation details. This section is optional. Exclude if nothing to add.

- **H3: Why Deploy [X] on Railway?**

  Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

  By deploying [X] on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.



# Publish and Share Templates
---
title: Publish and Share Templates
description: Learn how to publish and share your Railway templates.
---

Once you create a template, you have the option to publish it. Publishing a template will add it to our <a href="https://railway.com/templates" target="_blank">template marketplace</a> for other users to deploy.

## Publishing a Template

After you create your template, simply click the publish button and fill out the form to publish your template.

<Image src="https://res.cloudinary.com/railway/image/upload/v1753243835/docs/reference/templates/mockup-1753242978376_skjt7w.png"
  alt="Template publishing form"
  layout="intrinsic"
  width={2004}
  height={3834}
  quality={80}
/>

You can always publish your template by going to the <a href="https://railway.com/workspace/templates" target="_blank">Templates page in your Workspace settings</a> and choose `Publish` next to the template you'd like to publish.

Optionally, you can add a demo project to your template. This will be used to showcase your template in a working project, and can be accessed by clicking on the `Live Demo` button in the template's overview page.

## Sharing your Templates

After you create your template, you may want to share your work with the public and let others clone your project. You are provided with the Template URL where your template can be found and deployed.

### Deploy on Railway Button

To complement your template, we also provide a `Deploy on Railway` button which you can include in your README or embed it into a website.

<Image src="https://res.cloudinary.com/railway/image/upload/v1676438967/docs/deploy-on-railway-readme_iwcjjw.png" width={714} height={467} alt="Example README with Deploy on Railway button" />

![https://railway.com/button.svg](https://railway.com/button.svg)
The button is located at [https://railway.com/button.svg](https://railway.com/button.svg).

#### Markdown

To render the button in Markdown, copy the following code and replace the template code with your desired template. If you'd like to help us attribute traffic to your template, replace `utm_campaign=generic` in the URL with your template name.

```md
[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/ZweBXA?utm_medium=integration&utm_source=button&utm_campaign=generic)
```

#### HTML

To render the button in HTML, copy the following code and replace the template code with your desired template. If you'd like to help us attribute traffic to your template, replace `utm_campaign=generic` in the URL with your template name.

```html
<a
  href="https://railway.com/new/template/ZweBXA?utm_medium=integration&utm_source=button&utm_campaign=generic"
  ><img src="https://railway.com/button.svg" alt="Deploy on Railway"
/></a>
```

### Examples

Here are some example templates from the <a href="https://railway.com/templates" target="_blank">template marketplace</a> in button form:
|Icon|Template|Button|
|:--:|:------:|:----:|
|<img src="https://devicons.railway.com/i/nodejs.svg" alt="Node" width="25" height="25" />|Node|[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/ZweBXA?utm_medium=integration&utm_source=button&utm_campaign=node)|
|<img src="https://devicons.railway.com/i/deno.svg" alt="Deno" width="25" height="25" />|Deno|[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/LsaSsU?utm_medium=integration&utm_source=button&utm_campaign=deno)|
|<img src="https://devicons.railway.com/i/bun.svg" alt="Bun" width="25" height="25" />|Bun|[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/gxxk5g?utm_medium=integration&utm_source=button&utm_campaign=bun)|
|<img src="https://devicons.railway.com/i/go.svg" alt="Gin" width="25" height="25" />|Gin|[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/dTvvSf?utm_medium=integration&utm_source=button&utm_campaign=gin)|
|<img src="https://devicons.railway.com/i/flask-dark.svg" alt="Flask" width="25" height="25" />|Flask|[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/zUcpux?utm_medium=integration&utm_source=button&utm_campaign=flask)|

## Kickback Program

If your published template is deployed into other users' projects, you are eligible for kickbacks based on your support engagement. Learn more about the [kickback program](/reference/templates#kickback-program).

## Template Verification

Templates are verified when the creator and maintainer of the technology becomes a partner and reviews the template.

If you are or have a relationship with the creator, please reach out to us by submitting the form on our [partners page](https://railway.com/partners).

---
title: Deploy a Template
description: Learn how to deploy Railway templates.
---
# Deploy a Template

Templates allow you to deploy a fully configured project that is automatically
connected to infrastructure.

You can find featured templates on our <a href="https://railway.com/templates" target="_blank">template marketplace</a>.

## Template Deployment Flow

To deploy a template -

- Find a template from the marketplace and click `Deploy Now`
- If necessary, configure the required variables, and click `Deploy`
- Upon deploy, you will be taken to your new project containing the template service(s)
  - Services are deployed directly from the defined source in the template configuration
  - After deploy, you can find the service source by going to the service's settings tab
  - Should you need to make changes to the source code, you will need to [eject from the template repo](#eject-from-template-repository) to create your own copy. See next section for more detail.

_Note: You can also deploy templates into existing projects, by clicking `+ New` from your project canvas and selecting `Template`._

## Getting Help with a Template

If you need help with a template you have deployed, you can ask the template creator directly:

1. Find the template page in our [marketplace](https://railway.com/templates)
2. Click **"Discuss this Template"** on the template details page
3. Your question will be posted to the template's queue where the creator can help

Template creators are notified when questions are posted and are incentivized to provide helpful responses through Railway's kickback program.

<Image src="https://res.cloudinary.com/railway/image/upload/v1764639364/Ask_the_Template_Creator_wwzlca.png" alt = "Ask the Template Creator" width={1538} height={1618} quality={100} />

## Eject from Template Repository

<Banner variant="info">
As of March 2024, the default behavior for deploying templates, is to attach to and deploy directly from the template repository.  Therefore, you will not automatically get a copy of the repository on deploy.  Follow the steps below to create a repository for yourself.
</Banner>

By default, services deployed from a template are attached to and deployed directly from the template repository. In some cases, you may want to have your own copy of the template repository.

Follow these steps to eject from the template repository and create a mirror in your own GitHub account.

1. In the [service settings](/overview/the-basics#service-settings), under Source, find the **Upstream Repo** setting
2. Click the `Eject` button
3. Select the appropriate GitHub organization to create the new repository
4. Click `Eject service`

## Updatable Templates

When you deploy any services from a template based on a GitHub repo, every time you visit the project in Railway, we will check to see if the project it is based on has been updated by its creator.

If it has received an upstream update, we will create a branch on the GitHub repo that was created when deploying the template, allowing for you to test it out within a PR deploy.

If you are happy with the changes, you can merge the pull request, and we will automatically deploy it to your production environment.

If you're curious, you can read more about how we built updatable templates in this <a href="https://blog.railway.com/p/updatable-starters" target="_blank">blog post</a>

_Note: This feature only works for services based on GitHub repositories. At this time, we do not have a mechanism to check for updates to Docker images from which services may be sourced._
