---
title: Cartas y Postales
layout: post
---

Me gusta escribir cartas. Me gusta enviar y recibir la palabra escrita. Ver las caligrafías. Escribí algunas cartas a lo largo de mi vida. Algunas las envié y otras no.  

<section class="posts">
        {% for post in site.categories.postal %}
        <div class="postal">
          <a href="{{site.baseurl}}{{post.url}}"><h3>{{post.title}}</h3></a>
		            <p>
            {{post.content}}
          </p>
        </div>
        {% endfor %}
      </section>
