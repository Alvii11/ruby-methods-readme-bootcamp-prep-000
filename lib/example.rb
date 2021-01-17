```ruby
def say_hello_world_ten_times
  phrase = "Hello World!"
  puts phrase
  puts phrase
  puts phrase
  puts phrase
  puts phrase
  puts phrase
  puts phrase
  puts phrase
  puts phrase
  puts phrase
end

File: `greeting.rb`

```ruby
def greeting
  puts "Hello World"
end

greeting
greeting
greeting
greeting
greeting
```

Save your file and run it with `ruby greeting.rb`. You'll see:

```bash
$ ruby greeting.rb
Hello World
Hello World
Hello World
Hello World
Hello World
$
```

The bareword `greeting` will execute the body of the defined method.

#### Writing Code vs Reading About Code

Let's end by talking briefly about one additional use of `#`. Programmers love
conventions, or agreed upon rules that help them talk to each other about code.
A common syntax convention for Ruby methods is to preface them with a `#`, and
in subsequent lessons, you might see method names written with a `#` in front of
them. For example, if a method is named 'greeting', rubyists will often refer to 
it as `#greeting`. This is so that other rubyists can instantly recognize it as 
a method, as opposed to a variable or a bareword or a class. But remember that 
when you write it in your code, it should be `greeting` and not `#greeting`.
