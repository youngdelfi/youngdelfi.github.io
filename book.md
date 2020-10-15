---
title: Book
layout: post
---

<section class="posts">
        {% for post in site.tags.book %}
        <div class="book">
          <a href="{{site.baseurl}}{{post.url}}"><h3>{{post.title}}</h3></a>
		            <p>
            {{post.content}}
          </p>
        </div>
        {% endfor %}
      </section>
